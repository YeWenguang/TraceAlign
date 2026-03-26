import json
import signal
import subprocess
import tempfile
from typing import Dict, Optional, List
import subprocess
import os
import re
import ast
import sys
import inspect

def timeout_handler(signum, frame):
    raise TimeoutError("Execution exceeded time limit.")


def has_input_statements(code: str) -> bool:
    """Auto-translated documentation for has_input_statements."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        print(f"Code parsing failed: {e}")
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "input":
            return True

        if isinstance(node, ast.Attribute) and node.attr == "stdin":
            return True

    return False


def remove_examples_and_tests(code):
    # Regular expression to match lines with the specified patterns
    pattern = re.compile(r'#\s*(Example|Test|example|test).*')

    # Split code into lines
    lines = code.split('\n')

    # Remove content after the matching patterns
    cleaned_lines = [re.sub(pattern, '', line) for line in lines]

    # Join the cleaned lines back into a single string
    cleaned_code = '\n'.join(cleaned_lines)
    return cleaned_code.strip()


def extract_function_name(code_str):
    """Auto-translated documentation for extract_function_name."""
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


# ============================================================
# ============================================================
def normalize_output(s: str) -> str:
    """Auto-translated documentation for normalize_output."""
    if s is None:
        return ""
    
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    
    lines = s.split('\n')
    lines = [line.rstrip(' \t') for line in lines]
    s = '\n'.join(lines)
    
    s = s.rstrip()
    
    return s


def check_correctness(problem, completion, timeout=10, completion_id=None, include_private=True):
    """Auto-translated documentation for check_correctness."""
    tests = []
    errors = []
    all_tests_passed = True
    code_file_path = "temp_code.py"

    code = remove_examples_and_tests(completion)
    function_name = extract_function_name(code)
    
    if not function_name:
        function_name = extract_function_name(problem.get('starter_code', ''))
    
    if not function_name:
        return {
            'passed': False,
            'tests': [],
            'errors': [{'test_in': '', 'expected_out': '', 'actual_out': '', 'passed': False, 'error': "Could not extract function name."}]
        }

    print(f"Detected function name: {function_name}")

    if not has_input_statements(completion) and function_name:
        # ==========================================
        # ==========================================
        wrapper_code = f"""
import ast
import sys
import inspect
import textwrap

{code}

if __name__ == "__main__":
    raw_input = sys.stdin.read().rstrip('\\r\\n')
    
    try:
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

        # ---------------------------------------------------------
        # ---------------------------------------------------------
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
        # ---------------------------------------------------------

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

        result = target_func(*final_args)
        print(result)

    except Exception as e:
        print(e, file=sys.stderr)
        exit(1)
"""
        code = wrapper_code
    
    with open(code_file_path, "w") as file:
        file.write(code)

    def run_test(test_in, expected_out):
        """Auto-translated documentation for run_test."""
        nonlocal all_tests_passed
        
        # ============================================================
        # ============================================================
        expected_val = expected_out[0]
        expected_str_raw = str(expected_val)
        expected_str = normalize_output(expected_str_raw)
        
        test_result = {
            'test_in': test_in,
            'expected_out': expected_str,
            'actual_out': None,
            'passed': False,
            'error': None
        }
        try:
            result = subprocess.run(
                ['python3', code_file_path],
                input=test_in,
                text=True,
                capture_output=True,
                timeout=timeout
            )
            
            # ============================================================
            # ============================================================
            actual_str_raw = result.stdout
            actual_str = normalize_output(actual_str_raw)
            test_result['actual_out'] = actual_str
            
            
            if actual_str == expected_str:
                test_result['passed'] = True
            else:
                try:
                    actual_num = float(actual_str)
                    expected_num = float(expected_str)
                    
                    if abs(actual_num - expected_num) < 1e-9:
                        test_result['passed'] = True
                    else:
                        test_result['passed'] = False
                except (ValueError, TypeError):
                    test_result['passed'] = False
            
            
            if not test_result['passed']:
                all_tests_passed = False
                # ============================================================
                # ============================================================
                if result.stderr.strip():
                    err_msg = result.stderr.strip()
                else:
                    err_msg = f"Output mismatch.\n  Expected: {repr(expected_str)}\n  Actual:   {repr(actual_str)}"
                test_result['error'] = err_msg
                errors.append(test_result)
            elif result.stderr.strip():
                test_result['error'] = result.stderr.strip()
                errors.append(test_result)
                
        except subprocess.TimeoutExpired:
            all_tests_passed = False
            test_result['error'] = "Time Limit Exceeded"
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
