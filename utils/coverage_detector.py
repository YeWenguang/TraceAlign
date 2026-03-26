import os
import sys
import tempfile
import coverage
import unittest
import subprocess
import ast
import shutil
from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class CoverageResult:
    score: float = 0.0
    covered_lines: List[int] = field(default_factory=list)
    missing_lines: List[int] = field(default_factory=list)
    missing_code_content: str = ""
    execution_logs: List[str] = field(default_factory=list)
    error_occurred: bool = False

def calculate_code_coverage(code_str: str, test_code_str: str, timeout_per_test: int = 2) -> CoverageResult:
    """Auto-translated documentation for calculate_code_coverage."""
    
    work_dir = tempfile.mkdtemp()
    work_dir = os.path.realpath(work_dir)
    
    runner_script = f"""
{code_str}

{test_code_str}

if __name__ == "__main__":
    import sys
    import unittest
    
    if len(sys.argv) < 3:
        sys.exit(0)
    
    try:
        cls_name = sys.argv[1]
        method_name = sys.argv[2]
        test_class = globals().get(cls_name)
        
        if not test_class:
            sys.exit(1)
            
        suite = unittest.TestSuite()
        suite.addTest(test_class(method_name))
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        sys.exit(0 if result.wasSuccessful() else 1)
    except Exception:
        sys.exit(1)
"""
    runner_path = os.path.join(work_dir, "runner.py")
    with open(runner_path, 'w', encoding='utf-8') as f:
        f.write(runner_script)

    source_lines_count = len(code_str.splitlines())
    logs = []
    
    try:
        test_class_name, test_methods = _parse_test_methods(test_code_str)
        if not test_methods:
            return CoverageResult(0.0, [], [], "", ["Error: No test methods found."], True)
        
        logs.append(f"Methods: {test_methods}")

        for method in test_methods:
            data_file = os.path.join(work_dir, f".coverage.{method}")
            cmd = [
                sys.executable, "-m", "coverage", "run",
                f"--data-file={data_file}",
                "--include", runner_path,
                runner_path,
                test_class_name,
                method
            ]
            
            try:
                proc = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=timeout_per_test,
                    cwd=work_dir
                )
                if proc.returncode == 0:
                    logs.append(f"SUCCESS: {method}")
                else:
                    logs.append(f"FAILED: {method}")
            except subprocess.TimeoutExpired:
                logs.append(f"TIMEOUT: {method}")
            except Exception as e:
                logs.append(f"ERROR: {method} {e}")

        cov = coverage.Coverage(data_file=os.path.join(work_dir, ".coverage"))
        try:
            cov.combine(data_paths=[work_dir], strict=False)
        except coverage.exceptions.NoSource:
             return CoverageResult(0.0, [], [], "", logs + ["Combine failed (No data)."], True)

        try:
            cov.load()
            analysis = cov.analysis(runner_path)
            
            # Coverage 4.x+ : (filename, executable, excluded, missing, missing_formatted) -> Len 5
            # Coverage < 4.0: (filename, executable, missing, missing_formatted)          -> Len 4
            
            if len(analysis) == 5:
                raw_executable = analysis[1]
                raw_missing = analysis[3]
            elif len(analysis) == 4:
                raw_executable = analysis[1]
                raw_missing = analysis[2]
            else:
                raw_executable = analysis[1]
                raw_missing = analysis[-2]

            all_executable = [int(n) for n in raw_executable]
            all_missing = [int(n) for n in raw_missing]
            
            source_executable = [x for x in all_executable if x <= source_lines_count]
            source_missing = [x for x in all_missing if x <= source_lines_count]
            
            total = len(source_executable)
            missing = len(source_missing)
            covered = total - missing
            
            score = round((covered / total) * 100, 2) if total > 0 else 0.0
            
            missing_content = _extract_code_segments(code_str, source_missing)
            
            return CoverageResult(
                score=score,
                covered_lines=list(set(source_executable) - set(source_missing)),
                missing_lines=source_missing,
                missing_code_content=missing_content,
                execution_logs=logs,
                error_occurred=False
            )
            
        except Exception as e:
            import traceback
            return CoverageResult(0.0, [], [], "", logs + [f"Analysis Crash: {e}", traceback.format_exc()], True)

    finally:
        if os.path.exists(work_dir):
             shutil.rmtree(work_dir)

def _parse_test_methods(test_code_str: str) -> Tuple[str, List[str]]:
    try:
        tree = ast.parse(test_code_str)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if "Test" in node.name or any(getattr(b, 'attr', '') == 'TestCase' for b in node.bases):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]
                    return node.name, methods
    except:
        pass
    return "TestCases", []

def _extract_code_segments(code_str: str, line_numbers: List[int]) -> str:
    lines = code_str.splitlines()
    extracted = []
    for num in sorted(line_numbers):
        if 1 <= num <= len(lines):
            extracted.append(f"Line {num}: {lines[num-1].strip()}")
    return "\n".join(extracted)

if __name__ == "__main__":
    s_code = """
def func(x):
    if x > 0:
        return 1
    else:
        return 0
"""
    t_code = """
import unittest
class T(unittest.TestCase):
    def test_1(self):
        func(1)
    def test_2(self):
        import time
        time.sleep(1.5)
        func(-1)
"""
    res = calculate_robust_coverage(s_code, t_code, timeout_per_test=1)
    print(f"Score: {res.score}%")
    print(res.execution_logs)