import json
import zlib
import base64
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import pickle
import zlib
import base64
import json
import traceback
from typing import List, Tuple


class TestType(Enum):
    STDIN = "stdin"
    FUNCTIONAL = "functional"

@dataclass
class Test:
    input: str
    output: str
    testtype: TestType

    def __post_init__(self):
        self.testtype = TestType(self.testtype)


def parse_test_cases(dataset_item):
    """Auto-translated documentation for parse_test_cases."""
    print("Raw private test case data type:", type(dataset_item["private_test_cases"]))
    print("First 100 characters of private test data:", dataset_item["private_test_cases"][:100])

    public_tests = json.loads(dataset_item["public_test_cases"])
    public_test_cases = [Test(**t) for t in public_tests]

    private_tests_raw = dataset_item["private_test_cases"]
    try:
        private_tests = json.loads(private_tests_raw)
    except:
        private_test_b64 = private_tests_raw.encode("utf-8")
        decompressed = zlib.decompress(base64.b64decode(private_test_b64))
        private_tests = pickle.loads(decompressed)
        private_tests = json.loads(json.dumps(private_tests))

    if isinstance(private_tests, str):
        private_tests = json.loads(private_tests)
    if not isinstance(private_tests, list):
        raise ValueError(f"Private test cases did not parse into a list: {type(private_tests)}")

    private_test_cases = [Test(**t) for t in private_tests]

    return public_test_cases, private_test_cases


def test_single_code_codeforces(
        dataset_item: dict,
        code: str,
        timeout: int = 5
) -> dict:
    """Auto-translated documentation for test_single_code_codeforces."""
    question_info = {
        "question_id": dataset_item["question_id"],
        "difficulty": dataset_item["difficulty"],
        "contest_date": datetime.fromisoformat(dataset_item["contest_date"])
    }

    public_tests, private_tests = parse_test_cases(dataset_item)
    all_tests = {
        "public": public_tests,
        "private": private_tests
    }

    results = {
        **question_info,
        "public_test_results": [],
        "private_test_results": [],
        "overall_pass": True
    }

    for case_type, test_cases in all_tests.items():
        for idx, test_case in enumerate(test_cases):
            try:
                if test_case.testtype == TestType.STDIN:
                    is_passed = run_stdin_code(code, test_case.input, test_case.output, timeout)
                else:
                    is_passed = run_functional_code(code, test_case.input, test_case.output, timeout)

                results[f"{case_type}_test_results"].append(is_passed)
                if not is_passed:
                    results["overall_pass"] = False
                    print(
                        f"Failure: {case_type} case {idx + 1} failed | input: {test_case.input[:50]} | expected output: {test_case.output[:50]}")
            except Exception as e:
                results[f"{case_type}_test_results"].append(False)
                results["overall_pass"] = False
                print(f"Warning: {case_type} case {idx + 1} raised an execution error: {str(e)[:100]}")

    return results


def run_stdin_code(code: str, stdin_input: str, expected_output: str, timeout: int) -> bool:
    """Auto-translated documentation for run_stdin_code."""
    import subprocess
    import sys

    cmd = [sys.executable, "-c", code]
    try:
        result = subprocess.run(
            cmd,
            input=stdin_input.encode("utf-8"),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PYTHONIOENCODING": "utf-8"},
            cwd="/tmp"
        )
        actual_output = result.stdout.strip()
        expected_output = expected_output.strip()
        return actual_output == expected_output
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def run_functional_code(code: str, func_input: str, expected_output: str, timeout: int) -> bool:
    """Auto-translated documentation for run_functional_code."""
    try:
        exec_code = f"{code}\nresult = eval(f'solution({func_input})')"
        local_vars = {}
        exec(exec_code, {}, local_vars)
        return str(local_vars["result"]) == expected_output.strip()
    except:
        return False
