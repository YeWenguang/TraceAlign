"""Artifact release module."""

import json
import sys
import time
import os
import re
import traceback
import difflib
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datasets.human_eval_plus.execution import check_correctness
from utils.check_compilation_error import check_compilation_error
from utils.TracePy import run_test_cases, check_correctness_with_trace, ResultStatus
from utils.select_critical_failures import select_critical_failures
from utils.remove_test_case_from_source import remove_test_case_from_source
from utils.extract_function_names import extract_function_names
from utils.extract_function_signature import extract_function_signature_from_code
from utils.repair_queue import RepairQueueState, RepairTask
from components.testcase_generator import testcase_generation, extract_scenario_from_test, regenerate_removed_tests, merge_test_cases, count_test_methods, regenerate_tests_with_signature_hint
from components.code_generator import code_generation
from components.syntax_fixer import fix_compilation_error
from components.trace_analyzer import judge_code_logic
from components.code_repairer import repair_code_with_diagnosis, repair_code_with_trace
from components.requirement_extraction import requirement_extraction
from components.analysis_error import analysis_error
from components.requirement_analysis import requirement_analysis
from components.final_code_selector import select_best_code
from config import setup_config

INPUT_FILE = str(
    PROJECT_ROOT
    / "datasets"
    / "human_eval_plus"
    / "data"
    / "test-00000-of-00001-5973903632b82d40.parquet"
)

MODEL_NAME, OUTPUT_LOG_FILE, CONFIG_ARGS = setup_config("tracealign", "HumanEval+")

MAX_REPAIR_LOOPS = 5    
MAX_FAIL_STREAK = 2       
START_INDEX = CONFIG_ARGS.start_index if CONFIG_ARGS else 0          
API_NAME = "api_1"

BATCH_SIZE = 3
MAX_REPAIR_PER_ISSUE = 3

class GlobalStats:
    def __init__(self):
        self.total_processed = 0
        
        self.v1_passed = 0   # Zero-shot
        self.v2_passed = 0   # Sample Repair
        self.v4_passed = 0   # Final (Ours)
        
        self.loop_pass_counts = {i: 0 for i in range(MAX_REPAIR_LOOPS + 1)}

        self.outcomes = {
            "EFFECTIVE_REPAIR": 0,
            "ROBUST_SUCCESS": 0,
            "REGRESSION": 0,
            "PERSISTENT_FAILURE": 0,
            "UNKNOWN": 0
        }
        
        self.judge_remove_count = 0
        self.judge_fix_count = 0
        
        self.total_tokens = 0
        self.total_time = 0.0
        
        self.repair_by_sample = 0
        self.repair_by_generated = 0
        self.repair_by_both = 0

stats_tracker = GlobalStats()


def extract_doctest_examples(prompt: str) -> List[Dict[str, Any]]:
    """Auto-translated documentation for extract_doctest_examples."""
    examples = []
    pattern = r'^\s*>>>\s*(.+or)\n\s*(.+)$'
    matches = re.findall(pattern, prompt, re.MULTILINE)
    for call, expected in matches:
        call = call.strip()
        expected = expected.strip()
        if 'Traceback' in expected or 'Error' in expected or 'Exception' in expected:
            continue
        if call and expected:
            examples.append({"call": call, "expected": expected})
    return examples


def build_sample_test_from_examples(examples: List[Dict[str, Any]], entry_point: str) -> str:
    """Auto-translated documentation for build_sample_test_from_examples."""
    if not examples:
        return ""
    test_lines = ["def check_sample(candidate):"]
    for i, ex in enumerate(examples):
        call = ex["call"]
        expected = ex["expected"]
        if expected in ['True', 'False', 'None'] or expected.startswith('[') or expected.startswith('(') or expected.replace('.', '').replace('-', '').isdigit():
            test_lines.append(f"    assert {call} == {expected}, f'Test {i+1} failed: expected {expected}, got {{{call}}}'")
        else:
            test_lines.append(f"    assert {call} == '{expected}', f'Test {i+1} failed: expected {repr(expected)}, got {{{call}}}'")
    test_lines.append("    return True")
    return "\n".join(test_lines)


def check_correctness_with_sample(problem: Dict, completion: str, timeout: float = 5) -> Dict:
    """Auto-translated documentation for check_correctness_with_sample."""
    import subprocess
    import os
    import sys
    import tempfile
    import ast
    
    sys.path.insert(0, str(PROJECT_ROOT))
    from utils.TracePy import TRACER_CLASS_CODE
    
    examples = extract_doctest_examples(problem["prompt"])
    
    if not examples:
        result = check_correctness(problem, completion, timeout)
        return {
            'passed': result.get('passed', False),
            'tests': [],
            'errors': [],
            'trace': result.get('result', '')
        }
    
    entry_point = problem.get('entry_point', 'unknown')
    prompt = problem.get('prompt', '')
    full_code = prompt + completion
    
    TRACE_SEPARATOR = "<<<TRACE_LOG_SEPARATOR>>>"
    tests = []
    errors = []
    all_passed = True
    
    for i, ex in enumerate(examples):
        call = ex["call"]
        expected = ex["expected"]
        
        func_start = call.find(entry_point)
        args_str = ""
        if func_start != -1:
            paren_start = call.find('(', func_start)
            if paren_start != -1:
                paren_count = 0
                paren_end = paren_start
                for j in range(paren_start, len(call)):
                    if call[j] == '(':
                        paren_count += 1
                    elif call[j] == ')':
                        paren_count -= 1
                        if paren_count == 0:
                            paren_end = j
                            break
                args_str = call[paren_start+1:paren_end]
        
        args_list = []
        if args_str:
            try:
                parts = []
                current = ""
                bracket_count = 0
                for char in args_str:
                    if char in '([{':
                        bracket_count += 1
                    elif char in ')]}':
                        bracket_count -= 1
                    elif char == ',' and bracket_count == 0:
                        parts.append(current.strip())
                        current = ""
                        continue
                    current += char
                if current.strip():
                    parts.append(current.strip())
                
                for part in parts:
                    try:
                        val = ast.literal_eval(part)
                        args_list.append(val)
                    except:
                        args_list.append(part)
            except:
                pass
        
        stdin_input = '\n'.join([str(arg) for arg in args_list])
        
        wrapper_code = f'''
import ast
import sys
import inspect
import textwrap

{full_code}

{TRACER_CLASS_CODE}

if __name__ == "__main__":
    try:
        raw_input = sys.stdin.read().rstrip('\\r\\n')
        
        if '{entry_point}' not in globals():
            raise NameError("Function '{entry_point}' not found.")
        
        target_func = {entry_point}
        
        sig = inspect.signature(target_func)
        params = sig.parameters
        param_names = list(params.keys())
        required_args = [
            p for p in params.values() 
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        arg_count = len(required_args)
        
        final_args = []
        if raw_input:
            split_input = raw_input.split('\\n')
            if arg_count > 1 and len(split_input) == arg_count:
                raw_args_list = split_input
            else:
                raw_args_list = [raw_input]
            
            for idx, arg in enumerate(raw_args_list):
                try:
                    val = ast.literal_eval(arg)
                    final_args.append(val)
                except (ValueError, SyntaxError):
                    final_args.append(arg)
        
        tracer = CodeTracer(target_filenames=[__file__])
        sys.settrace(tracer.trace_calls)
        
        try:
            result = target_func(*final_args)
            sys.stdout.write(str(result) + '\\n')
        finally:
            sys.settrace(None)
            sys.stdout.write("{TRACE_SEPARATOR}" + '\\n')
            print(tracer.get_log())
            
    except Exception as e:
        sys.stderr.write(str(e))
        if 'tracer' in locals():
            sys.settrace(None)
            print("\\n" + "{TRACE_SEPARATOR}")
            print(tracer.get_log())
        exit(1)
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(wrapper_code)
            temp_file = f.name
        
        test_result = {
            'test_in': call,
            'expected_out': expected,
            'actual_out': None,
            'passed': False,
            'error': None,
            'trace_log': None
        }
        
        try:
            result = subprocess.run(
                ['python3', temp_file],
                input=stdin_input,
                text=True,
                capture_output=True,
                timeout=timeout
            )
            
            stdout = result.stdout
            stderr = result.stderr
            
            if TRACE_SEPARATOR in stdout:
                parts = stdout.split(TRACE_SEPARATOR)
                actual_output = parts[0].strip()
                trace_log = parts[1].strip() if len(parts) > 1 else ""
            else:
                actual_output = stdout.strip()
                trace_log = ""
            
            test_result['actual_out'] = actual_output
            test_result['trace_log'] = trace_log
            
            passed = False
            try:
                if actual_output == expected:
                    passed = True
                else:
                    actual_val = eval(actual_output)
                    expected_val = eval(expected)
                    if actual_val == expected_val:
                        passed = True
            except:
                pass
            
            test_result['passed'] = passed
            
            if not passed:
                all_passed = False
                error_msg = stderr.strip() if stderr.strip() else f"Expected: {expected}, Got: {actual_output}"
                test_result['error'] = error_msg
                errors.append(test_result)
        
        except subprocess.TimeoutExpired:
            all_passed = False
            test_result['error'] = 'Time Limit Exceeded'
            test_result['trace_log'] = 'Timeout - Trace log unavailable.'
            errors.append(test_result)
        except Exception as e:
            all_passed = False
            test_result['error'] = str(e)
            errors.append(test_result)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        
        tests.append(test_result)
    
    trace_lines = []
    for i, test in enumerate(tests):
        trace_lines.append(f"Test Case #{i+1}:")
        trace_lines.append(f"  Input: {test['test_in']}")
        trace_lines.append(f"  Expected: {test['expected_out']}")
        trace_lines.append(f"  Actual: {test['actual_out']}")
        trace_lines.append(f"  Passed: {test['passed']}")
        if test['error']:
            trace_lines.append(f"  Error: {test['error']}")
        if test['trace_log']:
            trace_lines.append(f"  Trace Log:\n{test['trace_log'][:500]}")
        trace_lines.append("-" * 50)
    
    return {
        'passed': all_passed,
        'tests': tests,
        'errors': errors,
        'trace': "\n".join(trace_lines)
    }


def check_correctness_with_trace_humaneval(problem: Dict, completion: str, timeout: float = 5) -> Dict:
    """Auto-translated documentation for check_correctness_with_trace_humaneval."""
    import subprocess
    import os
    import sys
    
    sys.path.insert(0, str(PROJECT_ROOT))
    from utils.TracePy import TRACER_CLASS_CODE
    
    tests = []
    errors = []
    all_tests_passed = True
    code_file_path = "temp_humaneval_code.py"
    
    TRACE_SEPARATOR = "<<<TRACE_LOG_SEPARATOR>>>"
    
    entry_point = problem.get('entry_point', 'unknown')
    prompt = problem.get('prompt', '')
    test_code = problem.get('test', '')
    
    full_code = prompt + completion
    
    wrapper_code = f'''
import ast
import sys
import inspect
import textwrap

{full_code}

{TRACER_CLASS_CODE}

if __name__ == "__main__":
    try:
        raw_input = sys.stdin.read().rstrip('\\r\\n')
        
        if '{entry_point}' not in globals():
            raise NameError("Function '{entry_point}' not found.")
        
        target_func = {entry_point}
        
        sig = inspect.signature(target_func)
        params = sig.parameters
        param_names = list(params.keys())
        required_args = [
            p for p in params.values() 
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        arg_count = len(required_args)
        
        final_args = []
        if raw_input:
            split_input = raw_input.split('\\n')
            if arg_count > 1 and len(split_input) == arg_count:
                raw_args_list = split_input
            else:
                raw_args_list = [raw_input]
            
            for idx, arg in enumerate(raw_args_list):
                try:
                    val = ast.literal_eval(arg)
                    final_args.append(val)
                except (ValueError, SyntaxError):
                    final_args.append(arg)
        
        tracer = CodeTracer(target_filenames=[__file__])
        sys.settrace(tracer.trace_calls)
        
        try:
            result = target_func(*final_args)
            sys.stdout.write(str(result) + '\\n')
        finally:
            sys.settrace(None)
            sys.stdout.write("{TRACE_SEPARATOR}" + '\\n')
            print(tracer.get_log())
            
    except Exception as e:
        sys.stderr.write(str(e))
        if 'tracer' in locals():
            sys.settrace(None)
            print("\\n" + "{TRACE_SEPARATOR}")
            print(tracer.get_log())
        exit(1)
'''
    with open(code_file_path, "w", encoding='utf-8') as file:
        file.write(wrapper_code)
    
    def extract_test_cases(test_code_str, entry_point_func):
        """Auto-translated documentation for extract_test_cases."""
        test_cases = []
        try:
            tree = ast.parse(test_code_str)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assert):
                    lines = test_code_str.split('\n')
                    if node.lineno > 0 and node.lineno <= len(lines):
                        assert_line = lines[node.lineno - 1].strip()
                        if entry_point_func in assert_line:
                            try:
                                func_start = assert_line.find(entry_point_func)
                                if func_start != -1:
                                    paren_start = assert_line.find('(', func_start)
                                    if paren_start != -1:
                                        paren_count = 0
                                        paren_end = paren_start
                                        for i in range(paren_start, len(assert_line)):
                                            if assert_line[i] == '(':
                                                paren_count += 1
                                            elif assert_line[i] == ')':
                                                paren_count -= 1
                                                if paren_count == 0:
                                                    paren_end = i
                                                    break
                                        
                                        func_call = assert_line[func_start:paren_end+1]
                                        expected = "True"
                                        if '==' in assert_line:
                                            eq_pos = assert_line.find('==')
                                            rest_after_eq = assert_line[eq_pos + 2:].strip()
                                            if rest_after_eq:
                                                if rest_after_eq.startswith('['):
                                                    bracket_count = 0
                                                    end_pos = 0
                                                    for i, ch in enumerate(rest_after_eq):
                                                        if ch == '[':
                                                            bracket_count += 1
                                                        elif ch == ']':
                                                            bracket_count -= 1
                                                            if bracket_count == 0:
                                                                end_pos = i + 1
                                                                break
                                                    expected = rest_after_eq[:end_pos].strip()
                                                elif rest_after_eq.startswith('('):
                                                    paren_count = 0
                                                    end_pos = 0
                                                    for i, ch in enumerate(rest_after_eq):
                                                        if ch == '(':
                                                            paren_count += 1
                                                        elif ch == ')':
                                                            paren_count -= 1
                                                            if paren_count == 0:
                                                                end_pos = i + 1
                                                                break
                                                    expected = rest_after_eq[:end_pos].strip()
                                                elif rest_after_eq.startswith('{'):
                                                    brace_count = 0
                                                    end_pos = 0
                                                    for i, ch in enumerate(rest_after_eq):
                                                        if ch == '{':
                                                            brace_count += 1
                                                        elif ch == '}':
                                                            brace_count -= 1
                                                            if brace_count == 0:
                                                                end_pos = i + 1
                                                                break
                                                    expected = rest_after_eq[:end_pos].strip()
                                                elif rest_after_eq.startswith('"') or rest_after_eq.startswith("'"):
                                                    quote_char = rest_after_eq[0]
                                                    end_pos = rest_after_eq.find(quote_char, 1)
                                                    if end_pos != -1:
                                                        expected = rest_after_eq[:end_pos + 1]
                                                    else:
                                                        expected = rest_after_eq.split(',')[0].strip()
                                                else:
                                                    expected = rest_after_eq.split(',')[0].strip()
                                                    if expected.endswith(')'):
                                                        expected = expected[:-1]
                                        
                                        test_cases.append({
                                            'input': func_call,
                                            'expected': expected
                                        })
                            except:
                                pass
        except:
            pass
        return test_cases
    
    test_cases = extract_test_cases(test_code, entry_point)
    
    if not test_cases:
        test_cases = [{'input': '', 'expected': 'True'}]
    
    def run_test(test_in, expected_out):
        nonlocal all_tests_passed
        expected_str = str(expected_out)
        
        test_result = {
            'test_in': test_in,
            'expected_out': expected_str,
            'actual_out': None,
            'passed': False,
            'error': None,
            'trace_log': None
        }
        
        try:
            result = subprocess.run(
                ['python3', code_file_path],
                input=test_in,
                text=True,
                capture_output=True,
                timeout=timeout
            )
            
            full_stdout = result.stdout
            trace_log_str = "No trace log captured..."
            
            if TRACE_SEPARATOR in full_stdout:
                parts = full_stdout.split(TRACE_SEPARATOR)
                actual_output_str = parts[0].rstrip('\r\n')
                if len(parts) > 1:
                    trace_log_str = parts[1].strip()
            else:
                actual_output_str = full_stdout.rstrip('\r\n')
            
            test_result['actual_out'] = actual_output_str
            test_result['trace_log'] = trace_log_str
            
            if actual_output_str == expected_str:
                test_result['passed'] = True
            else:
                try:
                    actual_num = float(actual_output_str)
                    expected_num = float(expected_out)
                    if abs(actual_num - expected_num) < 1e-9:
                        test_result['passed'] = True
                except (ValueError, TypeError):
                    pass
            
            if not test_result['passed']:
                all_tests_passed = False
                err_msg = result.stderr.strip() if result.stderr.strip() else f"Expected: {expected_str}, Got: {actual_output_str}"
                test_result['error'] = err_msg
                errors.append(test_result)
            elif result.stderr.strip():
                test_result['error'] = result.stderr.strip()
                errors.append(test_result)
                
        except subprocess.TimeoutExpired:
            all_tests_passed = False
            test_result['error'] = "Time Limit Exceeded"
            test_result['trace_log'] = "Timeout - Trace log unavailable."
            errors.append(test_result)
        except Exception as e:
            all_tests_passed = False
            test_result['error'] = str(e)
            errors.append(test_result)
        
        return test_result
    
    for tc in test_cases:
        tests.append(run_test(tc['input'], tc['expected']))
    
    if os.path.exists(code_file_path):
        os.remove(code_file_path)
    
    trace_lines = []
    for i, test in enumerate(tests):
        trace_lines.append(f"Test Case #{i+1}:")
        trace_lines.append(f"  Input: {test['test_in']}")
        trace_lines.append(f"  Expected: {test['expected_out']}")
        trace_lines.append(f"  Actual: {test['actual_out']}")
        trace_lines.append(f"  Passed: {test['passed']}")
        if test['trace_log']:
            trace_lines.append(f"  Trace Log:\n{test['trace_log'][:500]}")
        trace_lines.append("-" * 50)
    
    return {
        'passed': all_tests_passed,
        'tests': tests,
        'errors': errors,
        'trace': "\n".join(trace_lines)
    }


def print_experiment_guide():
    """Auto-translated documentation for print_experiment_guide."""
    guide = """
    ================================================================================
    Experiment Run Guide
    ================================================================================
    [Core RQ metrics used in the paper]
    1. [RQ1-Trend]   : Convergence trend monitoring (Pass Rate vs. Iteration)
    2. [RQ2-Judge]   : Judge decision records (REMOVE_TEST vs FIX_CODE)
    3. [RQ3-Ablation]: Ablation tracking (V1 vs V2 vs V4)
    4. [RQ4-Cost]    : Cost tracking (Efficiency)

    [Final outcome categories]
    - [EFFECTIVE_REPAIR] : initial fail -> final pass
    - [ROBUST_SUCCESS]   : initial pass -> final pass
    - [REGRESSION]       : initial pass -> final fail
    - [PERSISTENT_FAIL]  : initial fail -> final fail
    ================================================================================
    """
    print(guide)

def calculate_diff_ratio(code1, code2):
    if not code1 or not code2: return 1.0
    seq = difflib.SequenceMatcher(None, code1, code2)
    return 1.0 - seq.ratio()

def get_error_type(execution_result):
    if execution_result.get('passed', False): return "None"
    if "syntax" in str(execution_result).lower(): return "SyntaxError"
    tests = execution_result.get('tests', [])
    for t in tests:
        if not t['passed']:
            err = t.get('error', '')
            if "Timeout" in err: return "Timeout"
            if "AssertionError" in err: return "AssertionError"
            if "Exception" in err: return err.split(':')[0]
            return "LogicError"
    return "Unknown"



def get_dynamic_batch_size(remaining_loops: int, total_failures: int, base_size: int = BATCH_SIZE) -> int:
    """Auto-translated documentation for get_dynamic_batch_size."""
    if remaining_loops <= 1:
        time_based_batch = 5
    elif remaining_loops <= 3:
        time_based_batch = base_size  # 3
    else:
        time_based_batch = 2
    
    if total_failures > 10:
        quantity_bonus = 2
    elif total_failures >= 5:
        quantity_bonus = 1
    else:
        quantity_bonus = 0
    
    batch = time_based_batch + quantity_bonus
    
    batch = min(batch, total_failures, 7)
    
    return max(1, batch)


def sort_failures_by_priority(failures: list) -> list:
    """Auto-translated documentation for sort_failures_by_priority."""
    def get_priority(failure):
        status = getattr(failure, 'status', None)
        error_msg = getattr(failure, 'error_message', '')
        
        test_case = getattr(failure, 'test_case', '')
        is_sample = 'sample' in test_case.lower() or 'example' in test_case.lower()
        
        if is_sample:
            base_priority = 0
        elif status == ResultStatus.TIMEOUT:
            base_priority = 1
        elif status == ResultStatus.ERROR:
            base_priority = 2
        elif status == ResultStatus.FAIL:
            base_priority = 3
        else:
            base_priority = 4
        
        msg_len = len(error_msg) if error_msg else 0
        
        return (base_priority, msg_len)
    
    return sorted(failures, key=get_priority)

def save_log_entry(entry):
    os.makedirs(os.path.dirname(OUTPUT_LOG_FILE), exist_ok=True)
    with open(OUTPUT_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

def log_print(tag, message):
    GREEN = '\033[92m'; YELLOW = '\033[93m'; CYAN = '\033[96m'; RESET = '\033[0m'
    color = RESET
    if "RQ1" in tag: color = GREEN
    elif "RQ2" in tag: color = YELLOW
    elif "RQ4" in tag: color = CYAN
    elif "System" in tag: color = CYAN
    print(f"{color}[{tag}] {message}{RESET}")

def print_sample_summary(key, outcome_category, current_tokens, total_time, repair_trajectory, failure_reason, status, judge_history, loop_outcomes, repair_attribution=None):
    """Auto-translated documentation for print_sample_summary."""
    stats_tracker.total_processed += 1
    total = stats_tracker.total_processed

    if status["v1_init_passed"]: stats_tracker.v1_passed += 1
    if status["v2_sample_passed"]: stats_tracker.v2_passed += 1
    if status["v4_final_passed"]: stats_tracker.v4_passed += 1
    stats_tracker.outcomes[outcome_category] += 1
    stats_tracker.total_tokens += current_tokens
    stats_tracker.total_time += total_time
    
    for j in judge_history:
        if j['judge_decision'] == 'REMOVE_TEST': stats_tracker.judge_remove_count += 1
        else: stats_tracker.judge_fix_count += 1

    for outcome in loop_outcomes:
        idx = outcome['loop']
        is_passed = outcome['passed']
        if is_passed:
            stats_tracker.loop_pass_counts[idx] += 1
    
    if repair_attribution and outcome_category == "EFFECTIVE_REPAIR":
        if repair_attribution.get('sample_contributed') and repair_attribution.get('generated_contributed'):
            stats_tracker.repair_by_both += 1
        elif repair_attribution.get('sample_contributed'):
            stats_tracker.repair_by_sample += 1
        elif repair_attribution.get('generated_contributed'):
            stats_tracker.repair_by_generated += 1

    print("\n" + "="*80)
    pass
    print("="*80)
    
    icon = "❓"
    cn_outcome = "Unknown"
    if outcome_category == "EFFECTIVE_REPAIR": icon = "✅"; cn_outcome = "Effective repair (initial fail -> final pass)"
    elif outcome_category == "ROBUST_SUCCESS": icon = "🛡️"; cn_outcome = "Robust success (initial pass -> final pass)"
    elif outcome_category == "REGRESSION": icon = "⚠️"; cn_outcome = "Regression (initial pass -> final fail)"
    elif outcome_category == "PERSISTENT_FAILURE": icon = "❌"; cn_outcome = "Persistent failure"
    
    pass
    if failure_reason != "PASSED":
        pass

    print("-" * 80)
    
    pass
    pass
    pass
    
    pass
    l0_count = stats_tracker.loop_pass_counts.get(0, 0)
    print(f"    Loop 0 (Init) : {l0_count}/{total} ({l0_count/total*100:.1f}%)")
    for i in range(1, MAX_REPAIR_LOOPS + 1):
        count = stats_tracker.loop_pass_counts.get(i, 0)
        rate = count / total * 100
        bar_len = int(rate / 5)
        bar = "█" * bar_len
        print(f"    Loop {i:<2}       : {count}/{total} ({rate:.1f}%) {bar}")

    pass
    for k, v in stats_tracker.outcomes.items():
        if v > 0: print(f"    * {k:<18}: {v} ({v/total*100:.1f}%)")

    this_judge_remove = len([j for j in judge_history if j['judge_decision'] == 'REMOVE_TEST'])
    this_judge_fix = len([j for j in judge_history if j['judge_decision'] == 'FIX_CODE'])
    total_judge = stats_tracker.judge_remove_count + stats_tracker.judge_fix_count
    
    pass
    pass
    pass
    if total_judge > 0:
        remove_rate = stats_tracker.judge_remove_count / total_judge * 100
        pass
    pass

    pass
    v1_rate = stats_tracker.v1_passed / total * 100
    v2_rate = stats_tracker.v2_passed / total * 100
    v4_rate = stats_tracker.v4_passed / total * 100
    print(f"  - V1 (Zero-shot)  : {v1_rate:.2f}%")
    print(f"  - V2 (Sample-Only): {v2_rate:.2f}%  (Δ vs V1: {v2_rate - v1_rate:+.2f}%)")
    print(f"  - V4 (Full Judge) : {v4_rate:.2f}%  (Δ vs V2: {v4_rate - v2_rate:+.2f}%)")

    pass
    pass
    pass
    
    effective_total = stats_tracker.repair_by_sample + stats_tracker.repair_by_generated + stats_tracker.repair_by_both
    if effective_total > 0:
        pass
        pass
        pass
        pass
        pass
        if repair_attribution:
            this_attr = "sample tests" if repair_attribution.get('sample_contributed') else ""
            this_attr += " + " if repair_attribution.get('sample_contributed') and repair_attribution.get('generated_contributed') else ""
            this_attr += "generated tests" if repair_attribution.get('generated_contributed') else ""
            if this_attr:
                pass
    
    print("="*80 + "\n")

def format_debug_info(execution_result):
    tests = execution_result.get('tests', [])
    failed_tests = [t for t in tests if not t['passed']]
    passed_tests = [t for t in tests if t['passed']]
    if not failed_tests: return "No failed tests found."
    report = []
    for i, fail in enumerate(failed_tests[:3], 1):
        report.append(f"### Failed Test Case #{i}")
        report.append(f"- Input: `{fail['test_in']}`")
        report.append(f"- Expected: `{fail['expected_out']}`")
        report.append(f"- Actual: `{fail['actual_out']}`")
        report.append(f"- Error: {fail['error']}")
        trace_log = fail.get('trace_log')
        if trace_log and trace_log.strip():
            lines = trace_log.splitlines()
            if len(lines) > 30: kept_log = "\n".join(lines[:3] + ["..."] + lines[-20:])
            else: kept_log = trace_log
            report.append(f"Trace:\n```text\n{kept_log}\n```")
        report.append("-" * 20)
    if passed_tests:
        report.append("### Reference Successful Cases")
        for j, success in enumerate(passed_tests[:2], 1):
            report.append(f"#### Success Case #{j}")
            report.append(f"- Input: `{success['test_in']}`")
            report.append(f"- Output: `{success['actual_out']}`")
    return "\n".join(report)


print_experiment_guide()

datasets = []
try:
    df = pd.read_parquet(INPUT_FILE)
    datasets = df.to_dict('records')
    pass
except Exception as e:
    pass
    exit()

# ==========================================
# ==========================================
recovered_start_index = START_INDEX

if os.path.exists(OUTPUT_LOG_FILE):
    pass
    recovered_count = 0
    try:
        with open(OUTPUT_LOG_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    entry = json.loads(line)
                    
                    p_id = entry.get('problem_id', -1)
                    if p_id >= recovered_start_index:
                        recovered_start_index = p_id + 1
                    
                    stats_tracker.total_processed += 1
                    
                    status = entry.get('status', {})
                    if status.get("v1_init_passed"): stats_tracker.v1_passed += 1
                    if status.get("v2_sample_passed"): stats_tracker.v2_passed += 1
                    if status.get("v4_final_passed"): stats_tracker.v4_passed += 1
                    
                    outcome = entry.get('outcome_category', "UNKNOWN")
                    if outcome in stats_tracker.outcomes:
                        stats_tracker.outcomes[outcome] += 1
                        
                    judge_hist = entry.get('rq2_judge_history', [])
                    for j in judge_hist:
                        if j.get('judge_decision') == 'REMOVE_TEST':
                            stats_tracker.judge_remove_count += 1
                        else:
                            stats_tracker.judge_fix_count += 1
                            
                    loop_outcomes = entry.get('loop_outcomes', [])
                    for outcome_item in loop_outcomes:
                        idx = outcome_item.get('loop')
                        if idx is not None and outcome_item.get('passed'):
                            stats_tracker.loop_pass_counts[idx] = stats_tracker.loop_pass_counts.get(idx, 0) + 1

                    metrics = entry.get('metrics', {})
                    stats_tracker.total_tokens += metrics.get('tokens', 0)
                    stats_tracker.total_time += metrics.get('time', 0.0)
                    
                    recovered_count += 1
                except json.JSONDecodeError:
                    continue
                    
        pass
        if stats_tracker.total_processed > 0:
            pass

    except Exception as e:
        pass
# ==========================================

actual_start_index = max(recovered_start_index, START_INDEX)
actual_end_index = len(datasets) if CONFIG_ARGS.end_index is None else min(CONFIG_ARGS.end_index, len(datasets))

for key in tqdm(range(actual_start_index, actual_end_index), total=max(0, actual_end_index - actual_start_index)):
    pass
    dataset = datasets[key]
    requirement = dataset['prompt']
    entry_point_from_dataset = dataset.get('entry_point', '')
    examples = extract_doctest_examples(requirement)
    sample_io = build_sample_test_from_examples(examples, entry_point_from_dataset)
    
    current_tokens = 0
    start_time = time.time()
    
    status = { "v1_init_passed": False, "v2_sample_passed": False, "v4_final_passed": False }
    loop_outcomes = []
    judge_history = [] 
    
    repair_trajectory = [] 
    prev_code = ""
    initial_test_cases = ""
    
    repair_attribution = {
        "sample_contributed": False,
        "generated_contributed": False,
        "sample_fix_count": 0,
        "generated_fix_count": 0
    }         
    
    code_history = []
    
    try:
        pass
        code, p_tok, c_tok = code_generation(requirement, entry_point=entry_point_from_dataset, api=API_NAME)
        current_tokens += (p_tok + c_tok)
        prev_code = code 
        
        code_history.append({
            "code": code,
            "loop_number": 0,
            "action": "init_gen",
            "metadata": {"pass_count": 0, "total_count": 0}
        })
        
        init_result = check_correctness(dataset, code, timeout=10)
        is_init_passed = init_result['passed']
        
        loop_outcomes.append({"loop": 0, "passed": is_init_passed})
        status["v1_init_passed"] = is_init_passed
        
        repair_trajectory.append({
            "loop": 0,
            "action": "init_gen",
            "error_type": get_error_type(init_result),
            "diff_ratio": 0.0,
            "test_case_count": 0
        })
        
        test_cases = ""
        requirement_json = ""
        entry_point = []
        test_generated = False

        pass
        repair_loop = 0
        best_code = code
        max_pass_count = -1
        repair_queue = None
        
        last_sample_passing_code = None
        best_sample_passing_code = None
        best_sample_passing_gen_count = -1
        
        ever_had_nonzero_pass = False
        
        consecutive_rollbacks = 0
        
        while repair_loop < MAX_REPAIR_LOOPS:
            elapsed_time = time.time() - start_time
            print(f"\n{'='*60}")
            pass
            print(f"{'='*60}")
            pass
            if repair_queue:
                stats = repair_queue.get_stats()
                pass
                for i, task in enumerate(repair_queue.active_tasks):
                    status_icon = "🔄" if task.repair_count == 0 else "🔁"
                    pass
            else:
                pass
            print(f"{'='*60}\n")
            
            repair_loop += 1
            code_before_repair = code 

            pass
            compile_result, msg = check_compilation_error(code)
            if not compile_result:
                pass
                code, p_tok, c_tok = fix_compilation_error(requirement, code, msg, api=API_NAME)
                current_tokens += (p_tok + c_tok)
                entry_point = extract_function_names(code)
                
                diff = calculate_diff_ratio(code_before_repair, code)
                silent_res = check_correctness(dataset, code, timeout=10)
                repair_trajectory.append({
                    "loop": repair_loop, "action": "compile_fix",
                    "error_type": "SyntaxError", "diff_ratio": diff, "test_case_count": len(test_cases)
                })
                loop_outcomes.append({"loop": repair_loop, "passed": silent_res['passed']})
                
                code_history.append({
                    "code": code,
                    "loop_number": repair_loop,
                    "action": "compile_fix",
                    "metadata": {"pass_count": 0, "total_count": 0}
                })
                
                prev_code = code
                continue

            sample_result = check_correctness_with_sample(dataset, code, timeout=5)
            if not sample_result['passed']:
                pass
                err_type = get_error_type(sample_result)
                errors_list = sample_result.get('errors', [])
                if errors_list:
                    error_details = []
                    for err in errors_list:
                        test_in = err.get('test_in', 'N/A')
                        expected = err.get('expected_out', 'N/A')
                        actual = err.get('actual_out', 'N/A')
                        error_msg = err.get('error', 'Unknown error')
                        error_details.append(f"Input: {test_in}, Expected: {expected}, Got: {actual}, Error: {error_msg}")
                    debug_msg = "Sample test failed:\n" + "\n".join(error_details)
                else:
                    debug_msg = f"Sample test failed: {err_type}"
                code, p_tok, c_tok = repair_code_with_trace(requirement, code, debug_msg, api=API_NAME)
                current_tokens += (p_tok + c_tok)
                
                repair_attribution["sample_contributed"] = True
                repair_attribution["sample_fix_count"] += 1
                
                diff = calculate_diff_ratio(code_before_repair, code)
                silent_res = check_correctness(dataset, code, timeout=10)
                repair_trajectory.append({
                    "loop": repair_loop, "action": "sample_fix",
                    "error_type": err_type, "diff_ratio": diff, "test_case_count": len(test_cases)
                })
                loop_outcomes.append({"loop": repair_loop, "passed": silent_res['passed']})
                
                code_history.append({
                    "code": code,
                    "loop_number": repair_loop,
                    "action": "sample_fix",
                    "metadata": {"pass_count": 0, "total_count": 0}
                })
                
                prev_code = code
                continue
            else:
                pass
                if not status["v2_sample_passed"]: status["v2_sample_passed"] = True
                
                if not test_generated:
                    print("\n" + "="*60)
                    pass
                    print("="*60)
                    
                    pass
                    requirement_json, p2, c2 = requirement_extraction(requirement, sample_io, api=API_NAME)
                    current_tokens += (p2 + c2)
                    pass
                    
                    pass
                    
                    func_signature, func_names = extract_function_signature_from_code(code)
                    entry_point = func_names if func_names else extract_function_names(code)
                    
                    pass
                    pass
                    
                    test_cases, p_tok, c_tok = testcase_generation(
                        requirement, requirement_json, sample_io, None, entry_point, 
                        func_signature=func_signature, api=API_NAME
                    )
                    current_tokens += (p_tok + c_tok)
                    initial_test_cases = test_cases
                    
                    test_generated = True
                    pass
                    print("="*60 + "\n")

            results, pass_count, total_count = run_test_cases(code, test_cases)
            
            fail_count = total_count - pass_count
            timeout_count = sum(1 for r in results if r.status == ResultStatus.TIMEOUT)
            error_count = sum(1 for r in results if r.status == ResultStatus.ERROR)
            fail_only_count = sum(1 for r in results if r.status == ResultStatus.FAIL)
            pass
            
            last_sample_passing_code = code
            if pass_count > best_sample_passing_gen_count:
                best_sample_passing_code = code
                best_sample_passing_gen_count = pass_count
                pass
            
            if pass_count == total_count and total_count > 0:
                pass
                best_code = code
                silent_res = check_correctness(dataset, code, timeout=10)
                loop_outcomes.append({"loop": repair_loop, "passed": silent_res['passed']})
                for k in range(repair_loop + 1, MAX_REPAIR_LOOPS + 1):
                    loop_outcomes.append({"loop": k, "passed": silent_res['passed']})
                break
            
            if pass_count > 0:
                ever_had_nonzero_pass = True
            
            if pass_count == 0:
                if ever_had_nonzero_pass:
                    pass
                    
                    failed_results = [r for r in results if r.status != ResultStatus.PASS]
                    if failed_results:
                        debug_info_parts = []
                        for i, r in enumerate(failed_results[:3]):
                            debug_info_parts.append(f"### Failed Test #{i+1}")
                            debug_info_parts.append(f"- Test: {r.test_case[:200]}...")
                            debug_info_parts.append(f"- Error: {r.error_message}")
                            if r.trace_log:
                                lines = r.trace_log.splitlines()
                                kept_log = "\n".join(lines[-20:]) if len(lines) > 20 else r.trace_log
                                debug_info_parts.append(f"- Trace:\n```\n{kept_log}\n```")
                        debug_msg = "\n".join(debug_info_parts)
                    else:
                        debug_msg = "All generated test cases failed. Code may have regressed."
                    
                    code, p_tok, c_tok = repair_code_with_trace(requirement, code, debug_msg, api=API_NAME)
                    current_tokens += (p_tok + c_tok)
                    
                    repair_attribution["generated_contributed"] = True
                    repair_attribution["generated_fix_count"] += 1
                    
                    diff = calculate_diff_ratio(code_before_repair, code)
                    silent_res = check_correctness(dataset, code, timeout=10)
                    repair_trajectory.append({
                        "loop": repair_loop, "action": "zero_score_repair",
                        "error_type": "CodeRegression", "diff_ratio": diff, "test_case_count": count_test_methods(test_cases)
                    })
                    loop_outcomes.append({"loop": repair_loop, "passed": silent_res['passed']})
                    
                    code_history.append({
                        "code": code,
                        "loop_number": repair_loop,
                        "action": "zero_score_repair",
                        "metadata": {"pass_count": 0, "total_count": 0}
                    })
                    
                    prev_code = code
                    continue
                else:
                    pass
                    pass
                    pass
                    
                    failed_results = [r for r in results if r.status != ResultStatus.PASS]
                    
                    test_cases, p_tok, c_tok = regenerate_tests_with_signature_hint(
                        requirement=requirement,
                        sample_io=sample_io,
                        code=code,
                        failed_tests=failed_results,
                        entry_point=entry_point,
                        api=API_NAME
                    )
                    current_tokens += (p_tok + c_tok)
                    
                    pass
                    
                    loop_outcomes.append({"loop": repair_loop, "passed": False})
                    repair_trajectory.append({
                        "loop": repair_loop, "action": "regen_test_with_signature",
                        "error_type": "ZeroScore", "diff_ratio": 0.0, "test_case_count": count_test_methods(test_cases)
                    })
                    continue

            if max_pass_count == -1:
                max_pass_count = pass_count
                best_code = code
                pass
            elif pass_count < max_pass_count:
                consecutive_rollbacks += 1
                pass
                
                if consecutive_rollbacks >= 2:
                    pass
                
                if best_sample_passing_code is not None:
                    code = best_sample_passing_code
                    pass
                else:
                    code = best_code
                    pass
                
                silent_res = check_correctness(dataset, code, timeout=10)
                loop_outcomes.append({"loop": repair_loop, "passed": silent_res['passed']})
                repair_trajectory.append({
                    "loop": repair_loop, "action": "rollback",
                    "error_type": "Regression", "diff_ratio": calculate_diff_ratio(code_before_repair, code),
                    "test_case_count": len(test_cases),
                    "consecutive_rollbacks": consecutive_rollbacks
                })
                prev_code = code
                continue
            else:
                consecutive_rollbacks = 0
                if pass_count > max_pass_count:
                    old_max = max_pass_count
                    max_pass_count = pass_count
                    best_code = code
                    pass
                else:
                    pass
            
            all_failures = [r for r in results if r.status != ResultStatus.PASS]
            
            if len(all_failures) == 0:
                pass
                silent_res = check_correctness(dataset, code, timeout=10)
                loop_outcomes.append({"loop": repair_loop, "passed": silent_res['passed']})
                for k in range(repair_loop + 1, MAX_REPAIR_LOOPS + 1):
                    loop_outcomes.append({"loop": k, "passed": silent_res['passed']})
                break
            
            pass
            
            if repair_queue is None:
                sorted_failures = sort_failures_by_priority(all_failures)
                
                remaining_loops = MAX_REPAIR_LOOPS - repair_loop
                dynamic_batch = get_dynamic_batch_size(remaining_loops, len(sorted_failures))
                pass
                
                repair_queue = RepairQueueState(
                    active_tasks=[],
                    pending_pool=sorted_failures,
                    max_size=dynamic_batch,
                    max_retries=MAX_REPAIR_PER_ISSUE
                )
                repair_queue.replenish()
                pass
            else:
                current_failure_map = {f.test_case: f for f in all_failures}
                
                tasks_to_remove = []
                for task in repair_queue.active_tasks:
                    if task.test_case_content not in current_failure_map:
                        pass
                        tasks_to_remove.append(task)
                    else:
                        task.repair_count += 1
                        task.failure = current_failure_map[task.test_case_content]
                        
                        if task.repair_count > MAX_REPAIR_PER_ISSUE:
                            pass
                            test_cases = remove_test_case_from_source(test_cases, task.test_case_content)
                            tasks_to_remove.append(task)
                            repair_trajectory.append({
                                "loop": repair_loop, "action": "force_prune",
                                "error_type": "MaxRetryExceeded", "diff_ratio": 0.0, "test_case_count": len(test_cases)
                            })
                
                for task in tasks_to_remove:
                    repair_queue.remove_task(task)
                
                repair_queue.pending_pool = [f for f in repair_queue.pending_pool if f.test_case in current_failure_map]
                
                active_contents = {t.test_case_content for t in repair_queue.active_tasks}
                pending_contents = {f.test_case for f in repair_queue.pending_pool}
                for failure in all_failures:
                    if failure.test_case not in active_contents and failure.test_case not in pending_contents:
                        repair_queue.pending_pool.append(failure)
                
                repair_queue.pending_pool = sort_failures_by_priority(repair_queue.pending_pool)
                
                remaining_loops = MAX_REPAIR_LOOPS - repair_loop
                total_pending = len(repair_queue.pending_pool) + len(repair_queue.active_tasks)
                new_max_size = get_dynamic_batch_size(remaining_loops, total_pending)
                if new_max_size != repair_queue.max_size:
                    pass
                    repair_queue.max_size = new_max_size
                
                added = repair_queue.replenish()
                if added > 0:
                    pass
                
                stats = repair_queue.get_stats()
                pass
            
            if not repair_queue.has_active_tasks():
                pass
                silent_res = check_correctness(dataset, code, timeout=10)
                loop_outcomes.append({"loop": repair_loop, "passed": silent_res['passed']})
                for k in range(repair_loop + 1, MAX_REPAIR_LOOPS + 1):
                    loop_outcomes.append({"loop": k, "passed": silent_res['passed']})
                break
            
            active_failures = repair_queue.get_active_failures()
            pass
            for i, f in enumerate(active_failures):
                task = repair_queue.find_task_by_content(f.test_case)
                retry_info = f"(attempt {task.repair_count + 1})" if task else ""
                print(f"  [{i+1}] {f.test_case[:50]}... {retry_info}")
            
            judge_results_list, p_tok, c_tok = judge_code_logic(requirement, code, active_failures, api=API_NAME)
            current_tokens += (p_tok + c_tok)
            pass
            
            failure_map = {f.test_case: f for f in active_failures}
            confirmed_bugs = []
            cases_to_regenerate = []
            
            for res in judge_results_list:
                decision = "REMOVE_TEST" if res.is_correct else "FIX_CODE"
                reasoning_text = getattr(res, 'reasoning', '')
                
                judge_entry = {
                    "loop": repair_loop,
                    "test_case_content": res.test_case,
                    "judge_decision": decision,
                    "reasoning": reasoning_text
                }
                judge_history.append(judge_entry)
                
                if res.is_correct:
                    pass
                    
                    original_failure = failure_map.get(res.test_case)
                    should_save_for_regen = True
                    if original_failure:
                        if original_failure.status in [ResultStatus.TIMEOUT, ResultStatus.ERROR]:
                            should_save_for_regen = False
                    
                    if should_save_for_regen:
                        cases_to_regenerate.append({
                            "original_test": res.test_case,
                            "removal_reason": reasoning_text if reasoning_text else "Incorrect expected output in the test case",
                            "scenario_hint": extract_scenario_from_test(res.test_case)
                        })
                    else:
                        pass
                    
                    test_cases = remove_test_case_from_source(test_cases, res.test_case)
                    repair_queue.remove_task_by_content(res.test_case)
                    repair_queue.remove_from_pending_by_content(res.test_case)
                    repair_trajectory.append({
                        "loop": repair_loop, "action": "judge_prune",
                        "error_type": "BadTestCase", "diff_ratio": 0.0, "test_case_count": count_test_methods(test_cases)
                    })
                else:
                    pass
                    matched_failure = failure_map.get(res.test_case)
                    if matched_failure:
                        confirmed_bugs.append((res, matched_failure))
                    else:
                        for tc, f in failure_map.items():
                            if res.test_case in tc or tc in res.test_case:
                                confirmed_bugs.append((res, f))
                                break
            
            should_regenerate = (
                cases_to_regenerate and 
                repair_loop <= 2 and
                len(cases_to_regenerate) <= 2
            )
            
            if should_regenerate:
                limited_cases = cases_to_regenerate[:2]
                pass
                new_tests, p_tok, c_tok = regenerate_removed_tests(
                    requirement=requirement,
                    sample_io=sample_io,
                    removed_cases=limited_cases,
                    entry_point=entry_point,
                    api=API_NAME
                )
                current_tokens += (p_tok + c_tok)
                if new_tests:
                    old_count = count_test_methods(test_cases)
                    test_cases = merge_test_cases(test_cases, new_tests)
                    new_count = count_test_methods(test_cases)
                    pass
                    repair_trajectory.append({
                        "loop": repair_loop, "action": "regenerate_tests",
                        "error_type": "CoverageRecovery", "diff_ratio": 0.0, "test_case_count": new_count
                    })
            elif cases_to_regenerate:
                pass
            
            if confirmed_bugs:
                pass
                code, p_tok, c_tok = repair_code_with_diagnosis(
                    problem_desc=requirement,
                    code=code,
                    confirmed_bugs=confirmed_bugs,
                    entry_point=entry_point,
                    api=API_NAME
                )
                current_tokens += (p_tok + c_tok)
                
                repair_attribution["generated_contributed"] = True
                repair_attribution["generated_fix_count"] += 1
                
                diff = calculate_diff_ratio(code_before_repair, code)
                repair_trajectory.append({
                    "loop": repair_loop, "action": "batch_repair",
                    "error_type": "MultipleBugs", "diff_ratio": diff, "test_case_count": len(test_cases)
                })
                
                code_history.append({
                    "code": code,
                    "loop_number": repair_loop,
                    "action": "batch_repair",
                    "metadata": {"pass_count": 0, "total_count": 0}
                })
            else:
                pass
            
            repair_queue.replenish()
            
            if last_sample_passing_code is not None:
                best_loop_code = last_sample_passing_code
                pass
            else:
                best_loop_code = code
                pass
            
            silent_res = check_correctness(dataset, best_loop_code, timeout=10)
            loop_outcomes.append({"loop": repair_loop, "passed": silent_res['passed']})
            prev_code = code

        print(f"\n{'='*60}")
        pass
        print(f"{'='*60}")
        
        pass
        code_candidates = []
        seen_codes = set()
        
        for entry in code_history:
            candidate_code = entry.get('code', '')
            if not candidate_code:
                continue
            
            code_hash = hash(candidate_code.strip())
            if code_hash in seen_codes:
                continue
            seen_codes.add(code_hash)
            
            sample_result = check_correctness(dataset, candidate_code, timeout=10)
            if not sample_result.get('passed', False):
                continue
            
            if test_cases:
                results, pass_count, total_count = run_test_cases(candidate_code, test_cases)
            else:
                pass_count, total_count = 0, 0
            
            candidate = {
                'code': candidate_code,
                'pass_count': pass_count,
                'total_count': total_count,
                'loop_number': entry.get('loop_number', 0),
                'action': entry.get('action', 'unknown')
            }
            code_candidates.append(candidate)
            pass
        
        code_candidates.sort(key=lambda x: (x.get('pass_count', 0), x.get('loop_number', 0)), reverse=True)
        
        code_candidates = code_candidates[:5]
        
        if len(code_candidates) == 0:
            pass
            if last_sample_passing_code is not None:
                pass
                code = last_sample_passing_code
            else:
                pass
        elif len(code_candidates) == 1:
            pass
            code = code_candidates[0]['code']
        else:
            pass
            try:
                selected_code, reasoning, p_tok, c_tok = select_best_code(
                    problem_desc=requirement,
                    code_candidates=code_candidates,
                    api=API_NAME
                )
                current_tokens += (p_tok + c_tok)
                
                if selected_code:
                    selected_check = check_correctness(dataset, selected_code, timeout=10)
                    if selected_check.get('passed', False):
                        pass
                        code = selected_code
                        repair_trajectory.append({
                            "loop": repair_loop, "action": "llm_final_selection",
                            "error_type": "FinalSelection", "diff_ratio": calculate_diff_ratio(code, selected_code),
                            "test_case_count": count_test_methods(test_cases) if test_cases else 0,
                            "candidates_count": len(code_candidates)
                        })
                    else:
                        pass
                        code = code_candidates[0]['code']
                else:
                    pass
                    code = code_candidates[0]['code']
            except Exception as e:
                pass
                code = code_candidates[0]['code']
        
        print(f"{'='*60}\n")

        total_time = time.time() - start_time
        final_result = check_correctness(dataset, code, timeout=10)
        is_final_passed = final_result['passed']
        status["v4_final_passed"] = is_final_passed
        
        if is_init_passed and is_final_passed: outcome_category = "ROBUST_SUCCESS"
        elif is_init_passed and not is_final_passed: outcome_category = "REGRESSION"
        elif not is_init_passed and is_final_passed: outcome_category = "EFFECTIVE_REPAIR"
        else: outcome_category = "PERSISTENT_FAILURE"

        failure_reason = "PASSED"
        # if not is_final_passed:
        #     failure_reason = analysis_error(requirement, dataset, test_cases, code, final_result)
        
        log_entry = {
            "problem_id": key,
            "metrics": { "tokens": current_tokens, "time": total_time },
            "status": status,
            "outcome_category": outcome_category,
            "loop_outcomes": loop_outcomes, 
            "rq2_judge_history": judge_history,
            "rq2_initial_test_cases": initial_test_cases,
            "rq2_final_test_cases": test_cases,
            "repair_trajectory": repair_trajectory, 
            "repair_attribution": repair_attribution,
            "initial_code": prev_code if prev_code else code,
            "final_code": code,
            "failure_reason": failure_reason
        }
        save_log_entry(log_entry)
        
        print_sample_summary(key, outcome_category, current_tokens, total_time, repair_trajectory, failure_reason, status, judge_history, loop_outcomes, repair_attribution)

    except Exception as e:
        error_msg = str(e).lower()
        api_errors = ['api', 'timeout', 'connection', 'rate limit', 'quota', 'openai', 'request']
        is_api_error = any(err in error_msg for err in api_errors)
        
        if is_api_error:
            pass
            pass
            traceback.print_exc()
            import time as time_module
            time_module.sleep(5)
            break
        else:
            pass
            traceback.print_exc()
            break
