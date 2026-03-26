import sys
import unittest
import io
import inspect
import traceback
import multiprocessing
import queue
import time
import types
import linecache
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Tuple, Deque, Optional
from collections import deque


class ResultStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass
class ExecutionResult:
    status: ResultStatus
    test_case_id: str
    test_case: str
    error_message: str
    trace_log: str = ""

    def __repr__(self):
        return f"[{self.status.name}] {self.test_case_id}"


class CodeTracer:
    def __init__(self, target_filenames, stop_event: multiprocessing.Event, msg_queue, test_id: str, head_limit=30,
                 tail_limit=120):
        self.target_filenames = target_filenames
        self.stop_event = stop_event
        self.msg_queue = msg_queue
        self.test_id = test_id

        try:
            self.test_method_name = test_id.split('.')[-1]
        except:
            self.test_method_name = test_id

        self.check_interval = 100
        self.step_counter = 0

        self.line_counts = {}
        self.head_limit = head_limit
        self.tail_limit = tail_limit
        self.head_buffer: List[str] = []
        self.tail_buffer: Deque[str] = deque(maxlen=tail_limit)

        self.skipped_log_entries = 0
        self.source_cache = {}
        self.has_dumped = False

    def cache_source(self, filename, source_code):
        self.source_cache[filename] = source_code.splitlines()

    def _safe_repr(self, val, max_len=50):
        try:
            if isinstance(val, str):
                if len(val) > max_len:
                    return repr(val[:max_len]) + f"...(len={len(val)})"
                return repr(val)
            r = repr(val)
            if len(r) > max_len:
                return r[:max_len] + "..."
            return r
        except Exception:
            return "<repr-error>"

    def trace_calls(self, frame, event, arg):
        if event != 'call': return
        return self.trace_lines

    def trace_lines(self, frame, event, arg):
        self.step_counter += 1
        if self.step_counter % self.check_interval == 0:
            if self.stop_event.is_set():
                self._emergency_dump_and_exit()

        if event != 'line': return

        co_filename = frame.f_code.co_filename
        if co_filename not in self.target_filenames: return

        lineno = frame.f_lineno
        line_key = f"{co_filename}_{lineno}"
        exec_count = self.line_counts.get(line_key, 0) + 1
        self.line_counts[line_key] = exec_count

        source_lines = self.source_cache.get(co_filename, [])
        line_content = source_lines[lineno - 1].strip() if 0 <= lineno - 1 < len(source_lines) else ""

        critical_keywords = ('if ', 'elif ', 'else:', 'return', 'break', 'continue', 'raise', 'yield', 'assert')
        is_critical = any(line_content.startswith(kw) or f' {kw}' in line_content for kw in critical_keywords)
        
        is_first_exec = (exec_count == 1)
        
        try:
            vars_dict = {}
            for k, v in frame.f_locals.items():
                if not k.startswith('__'):
                    vars_dict[k] = self._safe_repr(v)
            vars_str = str(vars_dict)
        except:
            vars_str = "{Error capturing vars}"
            vars_dict = {}
        
        last_vars = getattr(self, '_last_vars', {})
        vars_changed = (vars_dict != last_vars)
        if vars_changed:
            self._last_vars = vars_dict.copy()

        should_log = False
        
        if is_critical:
            should_log = True
        elif is_first_exec:
            should_log = True
        elif vars_changed and exec_count <= 50:
            should_log = True
        elif exec_count <= 5:
            should_log = True
        elif exec_count <= 50:
            if exec_count % 10 == 0: should_log = True
        elif exec_count <= 500:
            if exec_count % 50 == 0: should_log = True
        else:
            if exec_count % 500 == 0: should_log = True

        if not should_log:
            return

        flags = []
        if is_critical: flags.append("⚡")
        if is_first_exec: flags.append("🆕")
        if vars_changed and not is_first_exec: flags.append("📝")
        flag_str = "".join(flags) if flags else ""

        count_suffix = f"(x{exec_count})" if exec_count > 1 else ""
        log_entry = f"{flag_str}Line {lineno:3} | {line_content[:30]:<30} | {vars_str} {count_suffix}"

        if len(self.head_buffer) < self.head_limit:
            self.head_buffer.append(log_entry)
        else:
            if len(self.tail_buffer) == self.tail_limit:
                self.skipped_log_entries += 1
            self.tail_buffer.append(log_entry)

    def _emergency_dump_and_exit(self):
        if self.has_dumped: return
        self.has_dumped = True

        sys.settrace(None)

        try:
            final_log = self.get_log(interrupted=True)
            final_log += "\n\n[TRACER]: Execution stopped due to timeout signal (Soft Stop)."

            res = ExecutionResult(
                status=ResultStatus.TIMEOUT,
                test_case_id=self.test_id,
                test_case=self.test_method_name,
                error_message="Timeout detected by Tracer (Infinite Loop suspected)",
                trace_log=final_log
            )

            self.msg_queue.put(res)
        except Exception:
            pass
        finally:
            sys.exit(0)

    def get_log(self, interrupted: bool = False) -> str:
        logs = []
        if self.head_buffer:
            logs.append("--- [TRACE HEAD] (Init Phase) ---")
            logs.extend(self.head_buffer)

        total_skipped = self.skipped_log_entries
        if total_skipped > 0:
            logs.append(f"\n... [BUFFER FULL - {total_skipped} LOGS DROPPED] ...\n")

        if self.tail_buffer:
            logs.append("--- [TRACE TAIL] (Pre-Interrupt) ---")
            logs.extend(self.tail_buffer)
            
        if interrupted:
            logs.append("\n" + "="*50)
            logs.append("📍>>> EXECUTION INTERRUPTED HERE <<<")
            logs.append("="*50)
            
        return "\n".join(logs)


def _run_single_case_process(
        code_str: str,
        test_code_str: str,
        target_test_id: str,
        msg_queue,
        stop_event: multiprocessing.Event
):
    USER_FILENAME = "<user_code>"
    TEST_FILENAME = "<test_code>"

    linecache.cache[TEST_FILENAME] = (len(test_code_str), None, test_code_str.splitlines(keepends=True), TEST_FILENAME)
    linecache.cache[USER_FILENAME] = (len(code_str), None, code_str.splitlines(keepends=True), USER_FILENAME)

    global_namespace = {}

    try:
        user_code_obj = compile(code_str, USER_FILENAME, 'exec')
        exec(user_code_obj, global_namespace)
    except Exception:
        msg_queue.put(ExecutionResult(ResultStatus.ERROR, target_test_id, "N/A",
                                      f"User Code Compilation Error:\n{traceback.format_exc()}"))
        return

    fake_module = types.ModuleType("solution")
    fake_module.__dict__.update(global_namespace)
    sys.modules["solution"] = fake_module

    try:
        test_code_obj = compile(test_code_str, TEST_FILENAME, 'exec')
        exec(test_code_obj, global_namespace)
    except Exception:
        msg_queue.put(ExecutionResult(ResultStatus.ERROR, target_test_id, "N/A",
                                      f"Test Code Compilation Error:\n{traceback.format_exc()}"))
        return

    method_name = "unknown_test"
    try:
        cls_name, method_name = target_test_id.split('.')
        test_cls = global_namespace.get(cls_name)
        test_instance = test_cls(method_name)
    except Exception:
        msg_queue.put(
            ExecutionResult(ResultStatus.ERROR, target_test_id, "N/A", f"Test Loader Error:\n{traceback.format_exc()}"))
        return

    tracer = CodeTracer(
        target_filenames={USER_FILENAME, TEST_FILENAME},
        stop_event=stop_event,
        msg_queue=msg_queue,
        test_id=target_test_id,
        head_limit=50,
        tail_limit=100
    )
    tracer.cache_source(USER_FILENAME, code_str)
    tracer.cache_source(TEST_FILENAME, test_code_str)

    capture_io = io.StringIO()
    sys.stdout = capture_io
    sys.stderr = capture_io

    status = ResultStatus.PASS
    err_msg = ""
    result_capture = unittest.TestResult()

    sys.settrace(tracer.trace_calls)
    try:
        test_instance.run(result_capture)
        if result_capture.errors:
            status = ResultStatus.ERROR
            err_msg = result_capture.errors[0][1]
        elif result_capture.failures:
            status = ResultStatus.FAIL
            err_msg = result_capture.failures[0][1]
    except SystemExit:
        return
    except Exception:
        status = ResultStatus.ERROR
        err_msg = traceback.format_exc()
    finally:
        sys.settrace(None)
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    final_log = tracer.get_log()
    res = ExecutionResult(
        status=status,
        test_case_id=target_test_id,
        test_case=method_name,
        error_message=err_msg,
        trace_log=final_log
    )
    msg_queue.put(res)


def _discovery_process(code_str, test_code_str, q):
    try:
        TEST_FILENAME = "<test_code>"
        global_namespace = {}
        try:
            exec(compile(code_str, "<user>", 'exec'), global_namespace)
        except:
            pass
        fake_module = types.ModuleType("solution")
        fake_module.__dict__.update(global_namespace)
        sys.modules["solution"] = fake_module
        exec(compile(test_code_str, TEST_FILENAME, 'exec'), global_namespace)
        loader = unittest.TestLoader()
        test_classes = [obj for name, obj in global_namespace.items() if
                        isinstance(obj, type) and issubclass(obj, unittest.TestCase)]
        tests_map = {}
        for cls in test_classes:
            for name in loader.getTestCaseNames(cls):
                tid = f"{cls.__name__}.{name}"
                tests_map[tid] = ""
        q.put(tests_map)
    except Exception as e:
        q.put(e)


def run_test_cases(code_str: str, test_code_str: str, timeout_per_case: int = 3) -> Tuple[
    List[ExecutionResult], int, int]:
    q_disc = multiprocessing.Queue()
    p_disc = multiprocessing.Process(target=_discovery_process, args=(code_str, test_code_str, q_disc))
    p_disc.start()
    p_disc.join(timeout=5)

    if p_disc.is_alive():
        p_disc.terminate()
        p_disc.join()
        return [ExecutionResult(ResultStatus.ERROR, "Global", "N/A", "Discovery Timeout")], 0, 1

    if q_disc.empty():
        return [ExecutionResult(ResultStatus.ERROR, "Global", "N/A", "Discovery Failed (Empty Queue)")], 0, 1

    discovery_res = q_disc.get()
    if isinstance(discovery_res, Exception):
        return [ExecutionResult(ResultStatus.ERROR, "Global", "N/A", str(discovery_res))], 0, 1

    tests_map = discovery_res
    final_results = []
    manager = multiprocessing.Manager()

    for test_id, test_source in tests_map.items():
        msg_queue = manager.Queue()
        stop_event = multiprocessing.Event()

        p_worker = multiprocessing.Process(
            target=_run_single_case_process,
            args=(code_str, test_code_str, test_id, msg_queue, stop_event)
        )
        p_worker.start()

        p_worker.join(timeout=timeout_per_case)

        if p_worker.is_alive():
            stop_event.set()

            p_worker.join(timeout=2.0)

            if p_worker.is_alive():
                p_worker.terminate()
                p_worker.join()

                if not msg_queue.empty():
                    final_results.append(msg_queue.get())
                else:
                    final_results.append(ExecutionResult(
                        status=ResultStatus.TIMEOUT,
                        test_case_id=test_id,
                        test_case=test_id.split('.')[-1],
                        error_message=f"Hard Timeout ({timeout_per_case}s). Worker process unresponsive despite Soft Stop signal.",
                        trace_log=""
                    ))
            else:
                if not msg_queue.empty():
                    final_results.append(msg_queue.get())
                else:
                    final_results.append(
                        ExecutionResult(ResultStatus.ERROR, test_id, "N/A", "Worker exited but returned no result.",
                                        ""))
        else:
            if not msg_queue.empty():
                final_results.append(msg_queue.get())
            else:
                final_results.append(ExecutionResult(
                    status=ResultStatus.ERROR,
                    test_case_id=test_id,
                    test_case="N/A",
                    error_message=f"Process Crashed (Exit Code: {p_worker.exitcode})",
                    trace_log=""
                ))

    manager.shutdown()
    pass_count = sum(1 for res in final_results if res.status == ResultStatus.PASS)

    return final_results, pass_count, len(final_results)





import ast
import inspect
import os
import re
import subprocess
import sys
import textwrap
from typing import Dict, Optional, List

TRACER_CLASS_CODE = r'''
class CodeTracer:
    def __init__(self, target_filenames, head_limit=50, tail_limit=100):
        self.target_filenames = target_filenames
        self.head_limit = head_limit
        self.tail_limit = tail_limit

        self.line_counts = {}
        self.head_buffer = []
        self.tail_buffer = [] 
        self.skipped_log_entries = 0
        self.source_cache = {}
        self._last_vars = {}

    def _safe_repr(self, val, max_len=50):
        try:
            if isinstance(val, str):
                if len(val) > max_len:
                    return repr(val[:max_len]) + f"...(len={len(val)})"
                return repr(val)
            r = repr(val)
            if len(r) > max_len:
                return r[:max_len] + "..."
            return r
        except Exception:
            return "<repr-error>"

    def trace_calls(self, frame, event, arg):
        if event != 'call': return
        return self.trace_lines

    def trace_lines(self, frame, event, arg):
        if event != 'line': return

        co_filename = frame.f_code.co_filename
        if co_filename not in self.target_filenames: return

        lineno = frame.f_lineno
        line_key = f"{co_filename}_{lineno}"
        exec_count = self.line_counts.get(line_key, 0) + 1
        self.line_counts[line_key] = exec_count

        if co_filename not in self.source_cache:
            try:
                with open(co_filename, 'r', encoding='utf-8') as f:
                    self.source_cache[co_filename] = f.readlines()
            except:
                self.source_cache[co_filename] = []

        source_lines = self.source_cache[co_filename]
        line_content = source_lines[lineno - 1].strip() if 0 <= lineno - 1 < len(source_lines) else ""

        if not line_content or line_content.startswith(('@', '#')):
            return

        critical_keywords = ('if ', 'elif ', 'else:', 'return', 'break', 'continue', 'raise', 'yield', 'assert')
        is_critical = any(line_content.startswith(kw) or f' {kw}' in line_content for kw in critical_keywords)
        
        is_first_exec = (exec_count == 1)
        
        try:
            vars_dict = {}
            for k, v in frame.f_locals.items():
                if not k.startswith('__') and k != 'target_func':
                    vars_dict[k] = self._safe_repr(v)
            vars_str = str(vars_dict)
        except:
            vars_str = "{Error capturing vars}"
            vars_dict = {}
        
        vars_changed = (vars_dict != self._last_vars)
        if vars_changed:
            self._last_vars = vars_dict.copy()

        should_log = False
        if is_critical:
            should_log = True
        elif is_first_exec:
            should_log = True
        elif vars_changed and exec_count <= 50:
            should_log = True
        elif exec_count <= 5:
            should_log = True
        elif exec_count <= 50:
            if exec_count % 10 == 0: should_log = True
        elif exec_count <= 500:
            if exec_count % 50 == 0: should_log = True
        else:
            if exec_count % 500 == 0: should_log = True

        if not should_log:
            return

        flags = []
        if is_critical: flags.append("⚡")
        if is_first_exec: flags.append("🆕")
        if vars_changed and not is_first_exec: flags.append("📝")
        flag_str = "".join(flags) if flags else ""

        count_suffix = f"(x{exec_count})" if exec_count > 1 else ""
        log_entry = f"{flag_str}Line {lineno:3} | {line_content[:30]:<30} | {vars_str} {count_suffix}"

        if len(self.head_buffer) < self.head_limit:
            self.head_buffer.append(log_entry)
        else:
            if len(self.tail_buffer) >= self.tail_limit:
                self.tail_buffer.pop(0)
                self.skipped_log_entries += 1
            self.tail_buffer.append(log_entry)

    def get_log(self) -> str:
        logs = []
        if self.head_buffer:
            logs.append("--- [TRACE HEAD] ---")
            logs.extend(self.head_buffer)

        if self.skipped_log_entries > 0:
            logs.append(f"\\n... [BUFFER FULL - {self.skipped_log_entries} LOGS DROPPED] ...\\n")

        if self.tail_buffer:
            logs.append("--- [TRACE TAIL] ---")
            logs.extend(self.tail_buffer)
        return "\\n".join(logs)
'''



def remove_examples_and_tests(code):
    pattern = re.compile(r'#\s*(Example|Test|example|test).*')
    lines = code.split('\n')
    cleaned_lines = [re.sub(pattern, '', line) for line in lines]
    return '\n'.join(cleaned_lines).strip()


def extract_function_name(code_str):
    try:
        tree = ast.parse(code_str)
        last_func_name = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                last_func_name = node.name
        if last_func_name:
            return last_func_name
    except Exception as e:
        print(f"AST extract failed: {e}, falling back to Regex.")
    matches = re.findall(r"def\s+(\w+)\s*\(", code_str)
    if matches:
        return matches[-1]
    return None


def has_input_statements(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "input":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "stdin":
            return True
    return False



def check_correctness_with_trace(problem, completion, timeout=10, completion_id=None, include_private=True):
    """Auto-translated documentation for check_correctness_with_trace."""
    tests = []
    errors = []
    all_tests_passed = True
    code_file_path = "temp_code.py"

    TRACE_SEPARATOR = "<<<TRACE_LOG_SEPARATOR>>>"

    code = remove_examples_and_tests(completion)
    function_name = extract_function_name(code)

    if not function_name:
        function_name = extract_function_name(problem.get('starter_code', ''))

    if not function_name:
        return {
            'passed': False,
            'tests': [],
            'errors': [{'test_in': '', 'expected_out': '', 'actual_out': '', 'passed': False,
                        'error': "Could not extract function name."}],
            'trace': 'No function found'
        }

    if not has_input_statements(completion) and function_name:
        wrapper_code = f"""
import ast
import sys
import inspect
import textwrap

{code}

{TRACER_CLASS_CODE}

if __name__ == "__main__":
    try:
        raw_input = sys.stdin.read().rstrip('\\r\\n')

        if '{function_name}' not in globals():
            raise NameError("Function '{function_name}' not found.")

        target_func = {function_name}

        sig = inspect.signature(target_func)
        params = sig.parameters
        param_names = list(params.keys())
        required_args = [
            p for p in params.values() 
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        arg_count = len(required_args)

        prefer_string_params = set()
        try:
            source = inspect.getsource(target_func)
            tree = ast.parse(textwrap.dedent(source))
            func_def = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
            for node in ast.walk(func_def):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'isinstance':
                    if len(node.args) == 2:
                        var_arg, type_arg = node.args
                        if isinstance(var_arg, ast.Name) and isinstance(type_arg, ast.Name) and type_arg.id == 'str':
                            if var_arg.id in param_names:
                                prefer_string_params.add(var_arg.id)
                if isinstance(node, ast.Attribute) and node.attr in ['isdigit', 'isalpha', 'lower', 'upper', 'startswith']:
                    if isinstance(node.value, ast.Name) and node.value.id in param_names:
                        prefer_string_params.add(node.value.id)
        except Exception:
            pass

        final_args = []
        split_input = raw_input.split('\\n')
        if arg_count > 1 and len(split_input) == arg_count:
            raw_args_list = split_input
        else:
            raw_args_list = [raw_input]

        for idx, arg in enumerate(raw_args_list):
            current_param = param_names[idx] if idx < len(param_names) else None
            try:
                val = ast.literal_eval(arg)
                if current_param in prefer_string_params and not isinstance(val, str):
                    final_args.append(arg)
                else:
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
"""
        code = wrapper_code

    with open(code_file_path, "w", encoding='utf-8') as file:
        file.write(code)

    def run_test(test_in, expected_out):
        nonlocal all_tests_passed
        expected_val = expected_out[0]
        expected_str = str(expected_val)

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
                    expected_num = float(expected_val)
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

    if 'sample_io' in problem:
        for sample in problem['sample_io']:
            tests.append(run_test(sample['input'], sample['output']))

    if include_private and 'test_list' in problem:
        for sample in problem['test_list']:
            tests.append(run_test(sample['input'], sample['output']))

    if os.path.exists(code_file_path):
        os.remove(code_file_path)

    return {
        'passed': all_tests_passed,
        'tests': tests,
        'errors': errors
    }



