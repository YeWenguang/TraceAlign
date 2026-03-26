import json
import sys
import subprocess
from subprocess import TimeoutExpired, CalledProcessError
import os
import shutil
from tempfile import mkdtemp
from contextlib import contextmanager
import multiprocessing
import platform
try:
    import resource
except ImportError:  # pragma: no cover - Windows fallback for help/import checks
    resource = None

@contextmanager
def create_tempdir():
    dirname = mkdtemp()
    try:
        yield dirname
    finally:
        shutil.rmtree(dirname)


def reliability_guard():
    dangerous_functions = [
        'os.kill', 'os.system', 'os.putenv', 'os.remove', 'os.removedirs',
        'shutil.rmtree', 'shutil.move', 'subprocess.Popen', 'sys.exit'
    ]
    for func in dangerous_functions:
        globals()[func] = None


def run_script(script, timeout):
    with create_tempdir() as dirname:
        script_path = os.path.join(dirname, 'temp_script.py')
        with open(script_path, 'w') as f:
            f.write(script)

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                timeout=timeout,
                check=True
            )
            return "All test cases passed."
        except TimeoutExpired:
            return "Test timeout after {} seconds.".format(timeout)
        except CalledProcessError as e:
            return f"Test failed with error:\n{e.stderr.decode()}"


def worker(script, timeout):
    reliability_guard()
    return run_script(script, timeout)


def check_correctness(problem, code, timeout=10, completion_id=None, use_full_test=False):
    """Auto-translated documentation for check_correctness."""
    if use_full_test:
        test_code = problem.get('test', '')
        if not test_code:
            test_code = "\n".join(problem.get('test_imports', [])) + "\n" + "\n".join(problem.get('test_list', []))
        script = code + "\n" + test_code
    else:
        script = code + "\n" + "\n".join(problem.get('test_imports', [])) + "\n" + "\n".join(
            problem.get('test_list', []))


    pool = multiprocessing.Pool(processes=1)
    result = pool.apply_async(worker, (script, timeout))
    try:
        status = result.get(timeout=timeout * 1.1)
        passed = status == "All test cases passed."
    except multiprocessing.TimeoutError:
        status = "Test did not complete in the given time."
        passed = False

    test_result = dict(
        task_id=problem["task_id"],
        passed=passed,
        result=status,
        completion_id=completion_id,
    )

    return test_result


if __name__ == "__main__":
    test_problem = {
        "task_id": 1,
        "text": "Write a function that returns the sum of two numbers",
        "code": """def similar_elements(test_tup1, test_tup2):
    return tuple(set(test_tup1) & set(test_tup2))""",
        "test_imports": [],
        "test_list": [
            "assert set(similar_elements((3, 4, 5, 6),(5, 7, 4, 10))) == set((4, 5))",
            "assert set(similar_elements((1, 2, 3, 4),(5, 4, 3, 7))) == set((3, 4))",
            "assert set(similar_elements((11, 12, 14, 13),(17, 15, 14, 13))) == set((13, 14))"
        ],
        "test": """import numpy as np
from math import inf

def is_floats(x) -> bool:
    # check if it is float; List[float]; Tuple[float]
    if isinstance(x, float):
        return True
    if isinstance(x, (list, tuple)):
        return all(isinstance(i, float) for i in x)
    if isinstance(x, np.ndarray):
        return x.dtype == np.float64 or x.dtype == np.float32
    return False


def assertion(out, exp, atol):
    if atol == 0 and is_floats(exp):
        atol = 1e-6
    out = set(out)
    exp = set(exp)
    if out != exp and atol != 0:
        assert np.allclose(out, exp, rtol=1e-07, atol=atol)
    else:
        assert out == exp, f"out: {out}, exp: {exp}"


inputs = [[(3, 4, 5, 6), (5, 7, 4, 10)], [(1, 2, 3, 4), (5, 4, 3, 7)], [(11, 12, 14, 13), (17, 15, 14, 13)], [(), ()], [(1, 2, 3), ()], [(), (4, 5, 6)], [(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), (11, 12, 13, 14, 15, 16, 17, 18, 19, 20)], [(1, 2, 2, 3, 3, 4, 4, 5, 5), (5, 5, 6, 6, 7, 7, 8, 8, 9, 9)], [(100, 200, 300, 400, 500), (100, 200, 400, 500)], [(10, 20, 30, 40, 50), (50, 60, 70, 80)], [(1, 2, 3, 4, 4, 5, 5), (4, 5, 6)], [(), (True, False, False, False, False, True)], [(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), (11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 15)], [(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), (11, 12, 13, 14, 15, 16, 17, 19, 20, 15)], [(1, 2, 3, 1), ()], [('kx', 'DHBNiditD'), (4, 5, 6)], [(1, 2, 2, 70, 3, 4, 4, 5, 5, 4, 3), (5, 5, 6, 6, 7, 7, 8, 8, 9, 9)], [(False, False, False, False, True), (False, False, False, False, False)], [(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)], [(8.514020219858878, -25.802494572247724, 5.873698915603498, 38.044354120134614, 11.222647627029431, 26.914534243589074, 78.41454157921689, -80.88414039955265), ('ceRuVEV', 'aAXslGdbD', 'DHBNiditD', 'fHRtFowQVh', 'ITntCqEvPi', 'SmJpP', 'DHBNiditD', 'kx', 'x')], [(False, False, False, False, False), (False, False, False, False, False)], [(), (5, 6)], [(1, 2, 2, 70, 3, 4, 4, 5, 5, 4, 3, 2), (1, 2, 2, 70, 3, 4, 4, 5, 5, 4, 3, 2)], [(1, 2, 3, 4, 5, 6, 12, 7, 8, 9, 0, 10), (1, 3, 4, 5, 6, 7, 8, 9, 0, 10)], [(1, 2, 3, 4, 5, 6, 12, 7, 8, 9, 0, 10, 10), (1, 3, 4, 5, 6, 7, 8, 9, 0, 10)], [(), (True, False, False, False)], [(4, 5, 16, 5), (1, 6, 3, 4, 4, 5, 5)], [('DRwvS', 'FdzAtAvnsS', 'ITntCqEvPi', 'nlUsIhET', 'ITntCqEvPi', 'x'), (True, False, True, False, True, False, True)], [(1, 2, 20), ()], [(11, 12, 13, 14, 15, 16, 17, 19, 20, 15), (11, 12, 13, 14, 15, 16, 17, 19, 20, 15)], [(1, 2, 3, 4, 5, 6, 12, 7, 8, 9, 0, 10, 10), (300, 1, 3, 4, 5, 6, 7, 8, 9, 0, 9)], [(False, False, False, False, False), (False, False, False, False)], [(1, 400, 3, 4, 4, 5, 5), (1, 400, 3, 4, 4, 5, 5, 5)], [(), (6,)], [(1, 2, 2, 3, 3, 4, 4, 5, 5), (5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 7)], [(1, 2, 3, 4, 5, 6, 7, 8, 9, 2, 10), (1, 2, 3, 4, 5, 6, 7, 8, 60, 10, 1)], [(1, 2, 3, 4, 5, 6, 7, 8, 9, 10), (1, 2, 3, 4, 4, 6, 7, 8, 9, 10)], [(1, 2, 2, 3, 3, 4, 4, 5, 5, 3), (5, 5, 6, 6, 7, 7, 8, 8, 9, 9)], [(100, 200, 300, 400, 500, 400, 300), (100, 200, 400, 500)], [('DRwvS', 'ITntCqEvPi', 'tUqF', 'ITntCqEvPi'), (4, 6, 6)], [(5, 2, 3), (1, 2, 3)], [(), (500, -45, 96, 22)], [(1, 2, 2, 70, 3, 4, 4, 5, 69, 5, 4, 3, 2), (1, 2, 2, 70, 3, 4, 4, 5, 69, 5, 4, 3, 2)], [(5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 7), (5, 5, 6, 6, 7, 7, 8, 8, 9, 9)], [(1, 2, 2, 2, 70, 3, 4, 4, 5, 5, 4, 3), (5, 5, 6, 6, 7, 7, 8, 8, 9, 9)], [(1, 2, 2, 3, 3, 4, 4, 5, 5, 3), (1, 2, 2, 3, 3, 4, 4, 5, 5, 3)], [('DRwvS', 'ITntCqEvPi', 'SmJpP', 'tUqF', 'ITntCqEvPi'), (4, 6, 6)], [(5, 5, 6, 6, 7, 8, 9, 9), (5, 5, 6, 6, 7, 7, 8, 9, 9)], [(1, 2, 20), (1, 2, 20)], [(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10), (11, 12, 13, 14, 15, 16, 17, 19, 20, 15)], [(12, 2, 20), (1, 2, 19)], [(11, 12, 13, 14, 15, 16, 17, 19, 20, 15), (11, 12, 13, 14, 15, 16, 17, 19, 20, 15, 20)], [(12, 2, 21), (12, 2, 20)], [(1, 2, 3, 5, 6, 12, 7, 8, 9, 10, 10), (1, 2, 3, 4, 5, 6, 12, 7, 8, 12, 0, 10, 10)], [(12, 2, 20, 20), (12, 2, 20)], [(6,), (6,)], [('LsgdJOGUO', 'nsDO', 'ceRuVEV', 'BohovaWqz', 'vovSNBB', 'BohovaWqz'), (True, False, False)], [('DRwvS', 'ITntCqEvPi', 'SmJpP', 'DRwvS'), ('DRwvS', 'ITntCqEvPi', 'SmJpP', 'tUqF', 'ITntCqEvPi')], [(300, 1, 3, 4, 5, 6, 8, 9, 0, 9), (300, 1, 3, 4, 5, 6, 7, 8, 9, 0, 9)], [(False, True, False, True, False, False, True, False, True), (False, True, False, True, False, False, True, False, True)], [(1, 2, 3, 4, 5, 6, 7, 8, 9), (11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 15)], [(1, 3, 2, 3), (1, 3, 2, 3)], [(False, False, False, False, False), (False, False, False, False, True, False)], [('kx', 'DHBNiditD', 'DHBNiditD'), (4, 5, 6)], [(1, 1, 2, 3, 1), ()], [(1, 2, 3, 5, 6, 6, 7, 8, 9, 10), (1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10)], [(1, 2, 3, 4, 5, 6, 7, -45, 8, 9, 2, 10), (1, 2, 3, 4, 5, 6, 7, 8, 9, 2, 10)], [(26, True, 26.914534243589074, -44), ()], [(11, 12, 13, 14, 15, 70, 17, 18, 19, 20, 15), (11, 12, 13, 14, 15, 70, 17, 18, 19, 20, 15)], [(300, 1, 3, 2, 4, 5, 6, 8, 9, 0, 9), (300, 1, 3, 4, 5, 6, 7, 8, 9, 0, 9)], [(100, 201, 300, 400, 500), (100, 200, 300, 400, 500)], [(1, 2, 3, 4, 5, 6, 12, 7, 8, 9, 0, 10, 10), (7, 1, 2, 3, 4, 5, 6, 12, 7, 8, 9, 0, 10, 10)], [(False, True, False, False), (False, False, False, False)], [(7, 1, 2, 3, 4, 4, 6, 12, 7, 8, 9, 0, 10, 10), (7, 1, 2, 3, 4, 5, 6, 12, 7, 8, 9, 0, 10, 10)], [(4, 16, 5), (4, 5, 16, 5)], [(1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 9), (1, 2, 3, 5, 6, 6, 7, 8, 9, 10)], [(11, 12, 13, 14, 15, 16, 17, 19, 20, 15), (11, 12, 13, 4, 15, 16, 17, 19, 20, 15, 20)], [(7, 7), (6,)], [(1, 2, 2, 3, 3, 4, 4, 5, 5, 3, 4), (5, 5, 6, 6, 7, 7, 8, 8, 9, 9)], [(100, 200, 300, 400, 500, 400, 300), (499, 200, 400, 500)], [(False, False, False, False, False, False), (False, False, False, False, False, False)], [(), (4, 6, 6)], [(4, 5, 6), (4, 4, 5, 6)], [(12, 2, 20, 20, 2), (12, 2, 20, 20)], [(11, 12, 13, 14, 15, 16, 17, 19, 20, 15, 11), (11, 12, 13, 14, 15, 16, 17, 19, 20, 15)], [(16, 1, 2, 3), (1, 2, 3)], [(1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 10), (1, 2, 3, 5, 6, 6, 7, 8, 9, 10)], [(30.445411706111912, 18.10848826924409, 24.97646124690165, -55.873347006206544), (500, -45, 96, 22)], [(12, 2, 20), (12, 2, 20, 20)], [(2, 3), (1, 2, 3)], [(1, 3, 2, 3), (1, 3, 3)], [(12, 20), (12, 18, 20)], [(False, False, False, False, False), (False, True, False, False, False, False)], [(4, 6, 6, 4), (4, 6, 6)], [(1, 1, 2, 3, 4, 5, 6, 7, 8, 9), (11, 15, 12, 13, 14, 15, 16, 17, 18, 19, 20, 16)], [(5, 5, 19, 6, 6, 7, 7, 8, 9, 9), (5, 5, 6, 6, 7, 7, 8, 9, 9)], [(5, 19, 5, 16, 5), (1, 6, 3, 4, 4, 5, 5)], [(-95.16136488545524, 8.514020219858878, -25.802494572247724, 5.873698915603498, 38.044354120134614, 11.222647627029431, 26.914534243589074, 78.41454157921689, -80.88414039955265), ('ceRuVEV', 'aAXslGdbD', 'DHBNiditD', 'fHRtFowQVh', 'ITntCqEvPi', 'SmJpP', 'DHBNiditD', 'kx', 'x')], [(100, 200, 300, 400), (100, 200, 300, 400)], [(1, 2, 20, 2), (1, 2, 20)], [(False, False, False, False), (False, True, False, False)], [(1, 2, 3, 4, 4, 6, 7, 8, 9, 10), (1, 2, 3, 4, 4, 6, 7, 8, 9, 10)], [(False, False, False, False), (False, True, False, False, True)], [(1, 400, 3, 4, 4, 5, 5, 5, 3), (1, 400, 3, 4, 12, 4, 5, 5, 5, 3)], [('DRwvS', 'ITntCqEvPi', 'SmJpP', 'tUqF', 'kx', 'tUqF'), ('DRwvS', 'ITntCqEvPi', 'SmJpP', 'tUqF', 'kx', 'tUqF')], [(1, 2, 3, 5, 6, 12, 7, 8, 9, 0, 10), (1, 3, 4, 5, 6, 7, 8, 9, 0, 10)], [('DRwvS', 'ITntCqEvPi', 'SmJpP', 'tUqF', 'kx', 'SmITntCqEvPiJpP', 'tUqF'), ('DRwvS', 'ITntCqEvPi', 'SmJpP', 'tUqF', 'kx', 'tUqF')], [(1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)], [(11, 12, 13, 14, 15, 26, 16, 17, 19, 20, 15), (11, 12, 13, 14, 15, 16, 17, 19, 20, 15)], [(5, 19, 5, 16, 5, 5), (5, 19, 5, 6, 5)], [(1, 2, 3, 6, 12, 7, 8, 9, 10, 10), (1, 2, 3, 5, 6, 12, 7, 8, 9, 10, 10)]]
results = [(4, 5), (3, 4), (13, 14), (), (), (), (), (5,), (200, 100, 500, 400), (50,), (4, 5), (), (), (), (), (), (5,), (False,), (1, 2, 3, 4, 5, 6, 7, 8, 9, 10), (), (False,), (), (1, 2, 3, 4, 5, 70), (0, 1, 3, 4, 5, 6, 7, 8, 9, 10), (0, 1, 3, 4, 5, 6, 7, 8, 9, 10), (), (4, 5), (), (), (11, 12, 13, 14, 15, 16, 17, 19, 20), (0, 1, 3, 4, 5, 6, 7, 8, 9), (False,), (1, 3, 4, 5, 400), (), (5,), (1, 2, 3, 4, 5, 6, 7, 8, 10), (1, 2, 3, 4, 6, 7, 8, 9, 10), (5,), (200, 100, 500, 400), (), (2, 3), (), (1, 2, 3, 4, 5, 70, 69), (5, 6, 7, 8, 9), (5,), (1, 2, 3, 4, 5), (), (5, 6, 7, 8, 9), (1, 2, 20), (), (2,), (11, 12, 13, 14, 15, 16, 17, 19, 20), (2, 12), (1, 2, 3, 5, 6, 7, 8, 10, 12), (2, 12, 20), (6,), (), ('SmJpP', 'ITntCqEvPi', 'DRwvS'), (0, 1, 3, 4, 5, 6, 8, 9, 300), (False, True), (), (1, 2, 3), (False,), (), (), (1, 2, 3, 5, 6, 7, 8, 9, 10), (1, 2, 3, 4, 5, 6, 7, 8, 9, 10), (), (70, 11, 12, 13, 14, 15, 17, 18, 19, 20), (0, 1, 3, 4, 5, 6, 8, 9, 300), (400, 100, 500, 300), (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12), (False,), (0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 12), (16, 4, 5), (1, 2, 3, 5, 6, 7, 8, 9), (11, 12, 13, 15, 16, 17, 19, 20), (), (5,), (200, 500, 400), (False,), (), (4, 5, 6), (2, 12, 20), (11, 12, 13, 14, 15, 16, 17, 19, 20), (1, 2, 3), (1, 2, 3, 5, 6, 7, 8, 9, 10), (), (2, 12, 20), (2, 3), (1, 3), (12, 20), (False,), (4, 6), (), (5, 6, 7, 8, 9), (5,), (), (200, 100, 400, 300), (1, 2, 20), (False,), (1, 2, 3, 4, 6, 7, 8, 9, 10), (False,), (1, 3, 4, 5, 400), ('SmJpP', 'DRwvS', 'tUqF', 'ITntCqEvPi', 'kx'), (0, 1, 3, 5, 6, 7, 8, 9, 10), ('SmJpP', 'DRwvS', 'tUqF', 'ITntCqEvPi', 'kx'), (1, 2, 3, 4, 5, 6, 7, 8, 9), (11, 12, 13, 14, 15, 16, 17, 19, 20), (19, 5), (1, 2, 3, 6, 7, 8, 9, 10, 12)]
for i, (inp, exp) in enumerate(zip(inputs, results)):
    assertion(similar_elements(*inp), exp, 0)"""
    }

    print("=" * 60)
    print("Test 1: correct code")
    print("=" * 60)
    correct_code = """def find_shared_elements(list1, list2):
    return list(set(list1) & set(list2))"""
    
    result = check_correctness(test_problem, correct_code, use_full_test=False)
    print(f"Sample tests: {'passed' if result['passed'] else 'failed'}")
    print(f"Result: {result['result']}")
    
    result = check_correctness(test_problem, correct_code, use_full_test=True)
    print(f"Full tests: {'passed' if result['passed'] else 'failed'}")
    print(f"Result: {result['result']}")


    print("\n" + "=" * 60)
    print("Testing complete!")
    print("=" * 60)
