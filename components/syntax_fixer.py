from typing import List, Dict, Any, Optional
from llm.client import call_openai_api, call_openai_api2
import json
import re
from dataclasses import dataclass
from utils.extract_code import extract_python_code
import logging
import ast
logger = logging.getLogger(__name__)


def check_code_completeness(code: str, is_stdin_problem: bool = False) -> dict:
    """Auto-translated documentation for check_code_completeness."""
    issues = []
    suggestions = []
    
    if not code or not code.strip():
        return {
            "is_complete": False,
            "issues": ["The code is empty"],
            "suggestions": ["Please generate valid Python code"]
        }
    
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        issues.append(f"Syntax error: {e}")
        suggestions.append(f"Fix the syntax error: {e}")
        return {
            "is_complete": False,
            "issues": issues,
            "suggestions": suggestions
        }
    
    func_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    if not func_defs:
        issues.append("No function definition was found in the code")
        suggestions.append("Add a main function to solve the problem")
    
    if not is_stdin_problem:
        for func in func_defs:
            has_return = any(isinstance(node, ast.Return) for node in ast.walk(func))
            if not has_return:
                issues.append(f"Function '{func.name}' has no return statement")
                suggestions.append(f"Add a return statement so function '{func.name}' returns a result")
    
    if is_stdin_problem:
        code_lower = code.lower()
        has_input_read = any(pattern in code for pattern in [
            'sys.stdin', 'input()', 'sys.argv', 'fileinput'
        ])
        has_main_block = 'if __name__' in code or '__main__' in code
        has_print = 'print(' in code
        
        if not has_input_read:
            issues.append("The stdin problem is missing input-reading code")
            suggestions.append("Add sys.stdin.read() or input() to read the input")
        
        if not has_main_block and func_defs:
            issues.append("The stdin problem is missing the main entry point")
            suggestions.append("Add an 'if __name__ == \"__main__\":' block to call the main function")
        
        if not has_print:
            issues.append("The stdin problem is missing an output statement")
            suggestions.append("Add a print() statement to output the result")
    
    boundary_patterns = [
        (r'range\s*\(\s*\w+\s*,\s*0\s*,\s*-1\s*\)', "range(x, 0, -1) does not execute when x = 0"),
        (r'\[\s*0\s*\]', "Direct access to [0] may raise IndexError"),
        (r'\[\s*-1\s*\]', "Accessing [-1] fails for an empty list"),
        (r'/\s*\w+\s*\)', "Division may trigger a division-by-zero error"),
    ]
    
    for pattern, warning in boundary_patterns:
        if re.search(pattern, code):
            issues.append(f"Potential boundary issue: {warning}")
            suggestions.append(f"Add a boundary-condition guard: {warning}")
    
    open_parens = code.count('(') - code.count(')')
    open_brackets = code.count('[') - code.count(']')
    open_braces = code.count('{') - code.count('}')
    
    if open_parens != 0:
        issues.append(f"Parentheses mismatch: {'extra ' + str(open_parens) + ' (' if open_parens > 0 else 'missing ' + str(-open_parens) + ' ('}")
    if open_brackets != 0:
        issues.append(f"Bracket mismatch: {'extra ' + str(open_brackets) + ' [' if open_brackets > 0 else 'missing ' + str(-open_brackets) + ' ['}")
    if open_braces != 0:
        issues.append(f"Brace mismatch: {'extra ' + str(open_braces) + ' {' if open_braces > 0 else 'missing ' + str(-open_braces) + ' {'}")
    
    return {
        "is_complete": len(issues) == 0,
        "issues": issues,
        "suggestions": suggestions
    }


def get_prompt_syntax_fixer(problem_desc, code, error_msg, is_stdin_problem=False, completeness_check=None):
    stdin_instruction = ""
    if is_stdin_problem:
        stdin_instruction = """
# 🚨 CRITICAL: This is a stdin/stdout problem (LiveCodeBench style)
- The code MUST read input from stdin (sys.stdin or input())
- The code MUST print output to stdout (print())
- Include `if __name__ == "__main__":` block to call the main function

**Example structure**:
```python
import sys

def solve():
    data = sys.stdin.read().strip().split()
    # Parse and process
    result = ...
    print(result)

if __name__ == "__main__":
    solve()
```
"""
    
    completeness_instruction = ""
    if completeness_check and not completeness_check.get("is_complete", True):
        issues = completeness_check.get("issues", [])
        suggestions = completeness_check.get("suggestions", [])
        completeness_instruction = f"""
# 🚨 CRITICAL: Code Completeness Issues Detected
The following issues were found in the code:
{chr(10).join(f'- {issue}' for issue in issues)}

Suggested fixes:
{chr(10).join(f'- {suggestion}' for suggestion in suggestions)}

**You MUST fix these issues in addition to the syntax error.**
"""
    
    boundary_instruction = """
# 🚨 CRITICAL: Edge Case Handling
When fixing the code, also ensure:
1. Empty list/string handling: Check `if not arr:` before accessing elements
2. Zero value handling: Ensure loops like `range(n, 0, -1)` work when n=0
3. Index safety: Add bounds checking before array access
4. Division safety: Check for zero before division
"""
    
    PROMPT_FIX_COMPILE_ERROR = f"""
# Role
You are an expert Python developer. Your task is to fix errors in the provided code.

# Input
[Problem Description]:
{problem_desc}

[Error Message]:
{error_msg}

[Broken Code]:
```python
{code}
```
{stdin_instruction}
{completeness_instruction}
{boundary_instruction}
# Instructions
1. **Analyze the error message** and identify the root cause.
2. **Fix the syntax error** (e.g., missing colons, mismatched parentheses, indentation errors).
3. **Fix completeness issues** if any were detected above.
4. **Add edge case handling** where appropriate.
5. Do NOT change the core algorithm logic unless necessary.
6. Output ONLY the corrected full Python code. Wrap it in ```python ... ``` blocks.

# Output Format
```python
# Your corrected code here
```
"""
    return PROMPT_FIX_COMPILE_ERROR


def fix_compilation_error(problem_desc: str, code: str, error_msg: str, api: str = "api_1", is_stdin_problem: bool = False) -> str:
    """Auto-translated documentation for fix_compilation_error."""
    completeness_check = check_code_completeness(code, is_stdin_problem)
    
    prompt = get_prompt_syntax_fixer(
        problem_desc=problem_desc,
        code=code,
        error_msg=error_msg,
        is_stdin_problem=is_stdin_problem,
        completeness_check=completeness_check
    )

    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)

    fixed_code = extract_python_code(llm_output)

    return fixed_code, prompt_tokens, completion_tokens

