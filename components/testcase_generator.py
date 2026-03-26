from llm.client import call_openai_api, call_openai_api2
from utils.parse_test_cases import parse_llm_test_cases
from utils.remove_comments import remove_comments
from utils.trim_long_docstrings import trim_long_docstrings
import logging
import re
logger = logging.getLogger(__name__)


def format_sample_io(sample_io) -> str:
    """Auto-translated documentation for format_sample_io."""
    if sample_io is None or sample_io == [] or sample_io == "" or sample_io == "[]":
        return "No sample I/O examples provided for this problem. Derive test cases from the [Problem Context] and [Test Blueprint] only."
    elif isinstance(sample_io, list) and len(sample_io) == 0:
        return "No sample I/O examples provided for this problem. Derive test cases from the [Problem Context] and [Test Blueprint] only."
    else:
        return sample_io


def get_prompt_unittest_generation1(requirements, requirement_json, sample_io, input_output, entry_point, func_signature: str = None):

    sample_io_formatted = format_sample_io(sample_io)

    # Filter out internal helper functions (starting with '_') from entry_point
    # These are private implementation details and should not be tested directly
    if isinstance(entry_point, list):
        public_entry_points = [ep for ep in entry_point if not ep.startswith('_')]
        # Use only public entry points, or fall back to original if none found
        entry_point_for_prompt = public_entry_points if public_entry_points else entry_point
        # Convert to comma-separated string for import statement
        if len(entry_point_for_prompt) == 1:
            entry_point_str = entry_point_for_prompt[0]
        else:
            entry_point_str = ', '.join(entry_point_for_prompt)
    else:
        # Single string entry_point
        entry_point_for_prompt = entry_point
        entry_point_str = entry_point if not entry_point.startswith('_') else entry_point

    temp = """{{}}"""

    prompt = f"""# Role
You are a Senior SDET. Your goal is to write a **clean, professional, and comprehensive** `unittest` suite.

# 🚨 Critical Directive 1: "Example-Led Authority"
**[Sample I/O] and [Examples] are the SUPREME AUTHORITY for input/output formats.**
- **Conflict Resolution**: If the [Problem Description] text conflicts with the [Example] blocks, the Examples override the text.
- **Exact Matching**: Do not simplify or change the container structure. Every bracket, parenthesis, and nesting level in the example is part of the required return signature.

# 🚨 Critical Directive 2: "Logic Authority" (Phase 2 Focus)
**The [Problem Context] Text is the SUPREME AUTHORITY for Logic Rules.**
- **Do not assume behavior based on function names.** (e.g., Just because a function is named `sort`, do not assume standard sorting unless the text says so. It might be a partial sort).
- **Strict Adherence**: If the text says "words <= 2 characters remain unchanged", you MUST verify they remain unchanged, even if standard English capitalization rules suggest otherwise.

# 🚨 Critical Directive 3: "Coverage & Granularity"
- **One-to-Many Mapping Allowed**: You are **NOT** restricted to a strict 1-to-1 mapping. A single scenario in the [Test Blueprint] **SHOULD** be split into multiple independent test methods if it covers distinct data points, boundary values, or variations.
- **Guideline**: Focus on being comprehensive. If a scenario implies multiple edge cases, write a separate test method for each.
- **Constraint**: 
    - **DO NOT merge** distinct Blueprint scenarios into a single test method.
    - **DO NOT skip** any Blueprint scenarios.

# 🚨 Critical Directive 4: "Invocation Protocol"
**Do NOT hallucinate a `Solution` class.**
- Most problems here are **standalone functions**.
- Only instantiate a class if the [Problem Context] explicitly shows `class Solution:`.
- Otherwise, invoke the imported function directly.

# 🚨 Critical Directive 5: "Pure Black-Box Testing"
**Do NOT implement ANY logic inside the test class.**
- **FORBIDDEN**: `sys.stdin`, `sys.stdout`, `io.StringIO` - NEVER use these in tests.
- **FORBIDDEN**: Reference implementations like `reference_solve()`, `reference_check()`, `expected_output()` - NEVER create your own solution.
- **FORBIDDEN**: Helper data structures (e.g., FenwickTree, BIT, SegmentTree) inside the test class.
- **REQUIRED**: Call the imported function directly with test inputs and compare against **hardcoded expected outputs**.
- If you cannot compute the expected output manually, use only the examples from [Sample I/O].
- Tests must be purely **black-box**: they verify behavior, not re-implement it.
- **NAMING RULE**: If you absolutely need a helper function for trivial operations (e.g., sorting output for comparison), it MUST start with `_` (underscore), e.g., `_sort_result()`. Functions NOT starting with `test_` or `_` will be removed.

# 🚨 Critical Directive 6: "Exception Testing Rules"
**ONLY test exceptions if EXPLICITLY required by the problem.**
- **FORBIDDEN**: Do NOT write tests that expect exceptions (`assertRaises`) unless the [Problem Context] explicitly states:
  - "The function should raise an exception when..."
  - "Throw an error for invalid input..."
  - "Must validate and reject..."
- **DEFAULT BEHAVIOR**: If the problem does NOT mention exception handling, assume the function should:
  - Return a valid result for valid inputs
  - Handle edge cases gracefully (return None, empty list, 0, etc.) rather than crashing
- **NO ASSUMPTIONS**: Do NOT assume "invalid input should throw exception" - this is often WRONG.
- **EXAMPLE**: If a problem asks to "find the maximum in a list", do NOT test that empty list throws an exception. Instead, test that it returns a sensible default or handles it gracefully.

# Two-Phase Analysis (CoT) - MANDATORY
You **MUST** perform this analysis in the output before writing Python code.

**Phase 1: IO & Type Audit (The "Wrapper" Check)**
1. Look at the code snippets in [Problem Context]. What is the return typeextra (e.g., `int`, `str`).
2. Look at [Sample I/O]. Is the output wrapped in a listor
3. **Decision**: Explicitly state the final Python return type you will expect in your assertions.

**Phase 2: Logic Extraction (The "Rule" Check)**
1. Read [Problem Context] carefully.
2. List the explicit **IF-THEN rules**. 
    - Example: "Rule A: If word length > 2 -> Capitalize."

**Phase 3: Test Data Pre-computation (The "Simulation")**
- For EACH Scenario ID in the [Test Blueprint], manually simulate the logic using the rules from Phase 2.
- **CRITICAL EXCEPTION**: If the logic involves complex calculations (e.g., bitwise ops, large math) where manual simulation is error-prone:
    - **DO NOT calculate the result manually.**
    - Explicitly state: "Logic is complex. Will use Reference Implementation Strategy in code."
- **Verification**: Double-check that your "Expected" strictly follows the Rule, not your intuition.

# Implementation Rules
1.  **Naming Convention**: Use **meaningful, descriptive snake_case names**.
2.  **Docstring Anchoring**: The **first line** of the docstring MUST be the Scenario ID.
3.  **Assertions**: Use `assertEqual(actual, expected)` for most cases.
4.  **Floating-Point Comparison**: For floating-point results, use `assertAlmostEqual(actual, expected, places=6)` or `assertAlmostEqual(actual, expected, delta=1e-6)` to handle precision issues.
5.  **No Implementation**: Write ONLY the test class.
6.  **Direct Call**: Call `{entry_point_str}(...)` directly inside tests. Do NOT write `Solution().{entry_point_str}(...)`.
7.  **"Hardcoded Expected Values" Strategy**: 
    - For ALL test cases, you MUST provide **hardcoded expected values** in assertions.
    - **DO NOT** create reference implementations, oracles, or helper functions that compute expected values.
    - If a calculation is too complex to compute manually, limit tests to values from [Sample I/O] or simple edge cases.
    - **EXCEPTION**: You MAY use a helper function ONLY for trivial operations like sorting a list or formatting output, but NEVER for core problem logic.
    
# User Data

[IO Specification]:
{input_output}

[Sample I/O]:
{sample_io_formatted}

[Test Blueprint]:
{requirement_json}

[Problem Context]:
{requirements}

[Target Function]:
{func_signature if func_signature else entry_point_str}

# Output Format
## Analysis (CoT)
[Phase 1 Analysis content]
[Phase 2 Analysis content]
[Phase 3 Analysis content - Step-by-step calculation]

## Python Code
```python
import unittest
from solution import {entry_point_str}

class TestSolution(unittest.TestCase):
    # test methods here
```
""" 
    return prompt

    
def testcase_generation(requirements: str, requirement_json: str, sample_io: str = None, input_output: str = None, entry_point: str = 'task_func', func_signature: str = None, api: str = "api_1"):
    """Auto-translated documentation for testcase_generation."""
    logger.info("Starting initial test generation...")
    
    prompt = get_prompt_unittest_generation1(requirements, requirement_json, sample_io, input_output, entry_point, func_signature)

    print(f"Test generation prompt:\n{prompt}")
        
    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)
    
    print(f"LLM output: {llm_output}")
    test_cases = extract_python_code(llm_output)
    
    test_cases = sanitize_python_code(test_cases)
    test_cases = remove_non_test_functions(test_cases, entry_point)
    test_cases = remove_comments(test_cases)
    test_cases = trim_long_docstrings(test_cases)
    print(f"Extracted test cases: {test_cases}")
    return test_cases, prompt_tokens, completion_tokens


def remove_non_test_functions(code_str: str, entry_point: str = None) -> str:
    """Auto-translated documentation for remove_non_test_functions."""
    if not code_str:
        return ""
    
    lines = code_str.split('\n')
    result = []
    skip_block = False
    skip_indent = -1
    skip_type = ""  # 'function' or 'class'
    
    allowed_helpers = {'setUp', 'tearDown', 'setUpClass', 'tearDownClass', 'setUpModule', 'tearDownModule'}
    
    forbidden_prefixes = ['reference_', 'expected_', 'oracle_', 'correct_', 'golden_']
    
    forbidden_class_patterns = [
        r'FenwickTree', r'BIT', r'SegmentTree', r'UnionFind', r'DisjointSet',
        r'Trie', r'SuffixTree', r'Heap', r'PriorityQueue', r'Graph',
        r'LinkedList', r'TreeNode', r'ListNode', r'Solution'
    ]
    forbidden_class_regex = re.compile(r'\bclass\s+(' + '|'.join(forbidden_class_patterns) + r')\b', re.IGNORECASE)
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        
        if skip_block:
            if stripped == '':
                i += 1
                continue
            if indent > skip_indent:
                i += 1
                continue
            else:
                skip_block = False
                skip_type = ""
        
        if stripped.startswith('class ') and indent > 0:
            class_match = forbidden_class_regex.search(stripped)
            if class_match:
                class_name = class_match.group(1)
                print(f"[Filter] Removed nested helper class '{class_name}': {stripped[:60]}...")
                skip_block = True
                skip_indent = indent
                skip_type = "class"
                i += 1
                continue
        
        if stripped.startswith('def '):
            func_match = re.match(r'def\s+(\w+)\s*\(', stripped)
            if func_match:
                func_name = func_match.group(1)
                
                should_remove = False
                reason = ""
                
                if entry_point:
                    if isinstance(entry_point, list):
                        if func_name in entry_point:
                            should_remove = True
                            reason = f"Matched entry_point list entry '{func_name}'"
                    elif func_name == entry_point:
                        should_remove = True
                        reason = f"Matched entry_point '{entry_point}'"
                
                if not should_remove:
                    for prefix in forbidden_prefixes:
                        if func_name.startswith(prefix):
                            should_remove = True
                            reason = f"Reference implementation function '{func_name}' (prefix '{prefix}')"
                            break
                
                if not should_remove:
                    lookahead_lines = []
                    for j in range(i + 1, min(i + 10, len(lines))):
                        la_line = lines[j]
                        la_stripped = la_line.lstrip()
                        la_indent = len(la_line) - len(la_stripped)
                        if la_stripped and la_indent <= indent:
                            break
                        lookahead_lines.append(la_stripped)
                    
                    lookahead_text = ' '.join(lookahead_lines).lower()
                    if 'notimplementederror' in lookahead_text or 'placeholder' in lookahead_text:
                        if not func_name.startswith('test_') and func_name not in allowed_helpers:
                            should_remove = True
                            reason = f"Placeholder function '{func_name}'"
                
                if not should_remove and not func_name.startswith('test_') and func_name not in allowed_helpers:
                    lookahead_lines = []
                    for j in range(i + 1, min(i + 50, len(lines))):
                        la_line = lines[j]
                        la_stripped = la_line.lstrip()
                        la_indent = len(la_line) - len(la_stripped)
                        if la_stripped and la_indent <= indent:
                            break
                        lookahead_lines.append(la_stripped)
                    
                    lookahead_text = ' '.join(lookahead_lines)
                    forbidden_io_patterns = ['sys.stdin', 'sys.stdout', 'io.StringIO', 'StringIO(']
                    for pattern in forbidden_io_patterns:
                        if pattern in lookahead_text:
                            should_remove = True
                            reason = f"Function '{func_name}' uses forbidden I/O pattern '{pattern}'"
                            break
                
                if not should_remove:
                    is_test_method = func_name.startswith('test_')
                    is_private_helper = func_name.startswith('_')
                    is_allowed_helper = func_name in allowed_helpers
                    
                    if not is_test_method and not is_private_helper and not is_allowed_helper:
                        should_remove = True
                        reason = f"Extra non-test function '{func_name}' that does not start with '_'"
                
                if should_remove:
                    print(f"[Filter] Removed {reason}: {stripped[:60]}...")
                    skip_block = True
                    skip_indent = indent
                    skip_type = "function"
                    i += 1
                    continue
        
        if not skip_block:
            result.append(line)
        i += 1
    
    return '\n'.join(result)


import re


def extract_python_code(text: str) -> str:
    """Auto-translated documentation for extract_python_code."""
    if not text:
        return ""

    pattern = r"```(or:python)or\s*(.*or)```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)

    if not matches:
        return ""

    best_code = ""
    max_score = -1

    for block in matches:
        block = block.strip()
        if not block:
            continue

        current_score = 0

        if "import unittest" in block or "unittest.TestCase" in block:
            current_score += 1000

        if "def test_" in block:
            current_score += 100

        current_score += len(block)

        if current_score > max_score:
            max_score = current_score
            best_code = block

    code = best_code

    if code:
        pattern_block = r"^if\s+__name__\s*==\s*['\"]__main__['\"]\s*:\s*\n\s*unittest\.main\s*\(.*or\).*"
        code = re.sub(pattern_block, '', code, flags=re.MULTILINE)

        pattern_line = r"^\s*unittest\.main\s*\(.*or\).*$"
        code = re.sub(pattern_line, '', code, flags=re.MULTILINE)

        pattern_comment = r"^\s*#.*$"
        code = re.sub(pattern_comment, '', code, flags=re.MULTILINE)

        code = re.sub(r'\n\s*\n', '\n', code)

        return code.strip()

    return ""


import ast
import re

def sanitize_python_code(code_str: str) -> str:
    """Auto-translated documentation for sanitize_python_code."""
    
    code_str = code_str.strip()
    if code_str.startswith("```python"):
        code_str = code_str[9:]
    elif code_str.startswith("```"):
        code_str = code_str[3:]
    if code_str.endswith("```"):
        code_str = code_str[:-3]
    
    code_str = code_str.strip()

    while True:
        try:
            ast.parse(code_str)
            return code_str
            
        except SyntaxError:
            if not code_str:
                return ""
            
            lines = code_str.splitlines()
            
            last_def_index = -1
            for i in range(len(lines) - 1, -1, -1):
                line_stripped = lines[i].strip()
                if line_stripped.startswith("def ") or line_stripped.startswith("class "):
                    last_def_index = i
                    break
            
            if last_def_index != -1:
                print(f"[Sanitizer] Syntax error detected. Removing the incomplete block starting at line {last_def_index+1}...")
                lines = lines[:last_def_index]
                code_str = "\n".join(lines)
            else:
                if len(lines) <= 1:
                    return ""
                lines = lines[:-1]
                code_str = "\n".join(lines)
            

def extract_test_class_name(code_str: str) -> str:
    """Auto-translated documentation for extract_test_class_name."""
    try:
        tree = ast.parse(code_str)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                is_test = "Test" in node.name
                if not is_test:
                    for base in node.bases:
                        if isinstance(base, ast.Attribute) and base.attr == 'TestCase':
                            is_test = True
                            break
                if is_test:
                    return node.name
    except:
        pass
    return None



def extract_scenario_from_test(test_case_code: str) -> str:
    """Auto-translated documentation for extract_scenario_from_test."""
    if not test_case_code:
        return "unknown test"
    
    method_name = None
    
    method_match = re.search(r'def (test_\w+)\(', test_case_code)
    if method_match:
        method_name = method_match.group(1)
    elif test_case_code.startswith('test_') and '(' not in test_case_code and '\n' not in test_case_code:
        method_name = test_case_code.strip()
    elif len(test_case_code) < 100 and '\n' not in test_case_code:
        method_name = test_case_code.strip()
    
    if not method_name:
        method_name = "unknown_test"
    
    readable_name = method_name.replace('test_', '').replace('_', ' ')
    
    if '\n' in test_case_code or 'def ' in test_case_code:
        input_match = re.search(r"['\"]([^'\"]{1,80})['\"]", test_case_code)
        sample_input = input_match.group(1) if input_match else ""
        
        expected_match = re.search(r"assertEqual\([^,]+,\s*([^\)]+)\)", test_case_code)
        expected_value = expected_match.group(1).strip() if expected_match else ""
        
        if sample_input and expected_value:
            return f"{readable_name}: input similar to '{sample_input[:40]}', expected output {expected_value[:30]}"
        elif sample_input:
            return f"{readable_name}: input similar to '{sample_input[:50]}'"
    
    return readable_name


def regenerate_removed_tests(requirement: str, sample_io: str, removed_cases: list, 
                              entry_point: str, api: str = "api_1") -> tuple:
    """Auto-translated documentation for regenerate_removed_tests."""
    if not removed_cases:
        return "", 0, 0
    
    removed_descriptions = "\n".join([
        f"- **Scenario {i+1}**: {case['scenario_hint']}\n  - Removal reason: {case['removal_reason'][:200]}"
        for i, case in enumerate(removed_cases)
    ])
    
    sample_io_formatted = format_sample_io(sample_io)
    
    prompt = f"""# Role
You are a test-case repair specialist. Generate **correct replacement tests** for the removed scenarios.

# Critical Requirements
1. Treat examples as the source of truth whenever examples conflict with abstract wording.
2. Keep the tests purely black-box. Do not implement solution logic inside the test class.
3. Use hardcoded expected outputs.
4. If helper functions are necessary, they must start with `_`.
5. Generate exactly one test method per removed scenario.

# Removed Scenarios
{removed_descriptions}

# Problem Description
{requirement}

# Sample I/O
{sample_io_formatted}

# Target Function
{entry_point}

# Generation Rules
1. Generate exactly one test method per scenario and avoid duplicates.
2. Match the sample I/O format and behavior precisely.
3. Manually derive every expected output.
4. Keep expected values consistent with the problem constraints.
5. For invalid-type checks, pass the raw invalid value directly (for example `{entry_point}(None)`).
6. Use snake_case names and output complete runnable unittest code.

```python
import unittest
from solution import {entry_point}

class TestRegenerated(unittest.TestCase):
    pass
```
"""
    
    logger.info(f"Generating replacement tests for {len(removed_cases)} removed scenarios...")
    
    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)

    print(f"Test repair prompt:\n{prompt}")
    print(f"Test repair output:\n{llm_output}")
    
    new_tests = extract_python_code(llm_output)
    new_tests = sanitize_python_code(new_tests)
    new_tests = remove_non_test_functions(new_tests, entry_point)
    new_tests = remove_comments(new_tests)
    
    logger.info("Successfully generated replacement tests")
    
    return new_tests, prompt_tokens, completion_tokens


def merge_test_cases(existing_tests: str, new_tests: str) -> str:
    """Auto-translated documentation for merge_test_cases."""
    if not new_tests or not new_tests.strip():
        return existing_tests
    
    if not existing_tests or not existing_tests.strip():
        return new_tests
    
    try:
        existing_tree = ast.parse(existing_tests)
        new_tree = ast.parse(new_tests)
        
        existing_class = None
        for node in existing_tree.body:
            if isinstance(node, ast.ClassDef) and "Test" in node.name:
                existing_class = node
                break
        
        if not existing_class:
            return existing_tests + "\n\n" + new_tests
        
        new_methods = []
        for node in new_tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                        new_methods.append(item)
        
        if not new_methods:
            return existing_tests
        
        existing_method_names = {
            item.name for item in existing_class.body 
            if isinstance(item, ast.FunctionDef)
        }
        
        added_count = 0
        for method in new_methods:
            if method.name not in existing_method_names:
                existing_class.body.append(method)
                existing_method_names.add(method.name)
                added_count += 1
        
        if added_count > 0:
            try:
                merged_code = ast.unparse(existing_tree)
                logger.info(f"Successfully merged {added_count} new test methods")
                return merged_code
            except AttributeError:
                logger.warning("This Python version does not support ast.unparse. Falling back to simple concatenation")
                return existing_tests + "\n\n# === Augmented Test Cases ===\n" + new_tests
        
        return existing_tests
        
    except SyntaxError as e:
        logger.warning(f"A syntax error occurred while merging test cases: {e}. Falling back to simple concatenation")
        return existing_tests + "\n\n# === Augmented Test Cases ===\n" + new_tests


def count_test_methods(test_code: str) -> int:
    """Auto-translated documentation for count_test_methods."""
    if not test_code:
        return 0
    return len(re.findall(r'def test_\w+\(', test_code))



def extract_function_signature(code: str, entry_point: str = None) -> str:
    """Auto-translated documentation for extract_function_signature."""
    if not code:
        return ""
    
    signatures = []
    
    pattern = r'^[ \t]*(def\s+(\w+)\s*\([^)]*\)(or:\s*->\s*[^:]+)or:)'
    
    for match in re.finditer(pattern, code, re.MULTILINE):
        full_signature = match.group(1).strip()
        func_name = match.group(2)
        
        if entry_point:
            if isinstance(entry_point, list):
                if func_name not in entry_point:
                    continue
            elif func_name != entry_point:
                continue
        
        if func_name.startswith('_') or func_name.startswith('test_'):
            continue
        
        signatures.append(full_signature)
    
    if signatures:
        return "\n".join(signatures)
    
    try:
        import ast
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                
                if func_name.startswith('_') or func_name.startswith('test_'):
                    continue
                
                if entry_point:
                    if isinstance(entry_point, list):
                        if func_name not in entry_point:
                            continue
                    elif func_name != entry_point:
                        continue
                
                args_parts = []
                for arg in node.args.args:
                    arg_name = arg.arg
                    if arg.annotation:
                        arg_type = ast.unparse(arg.annotation)
                        args_parts.append(f"{arg_name}: {arg_type}")
                    else:
                        args_parts.append(arg_name)
                
                args_str = ", ".join(args_parts)
                
                if node.returns:
                    return_type = ast.unparse(node.returns)
                    signatures.append(f"def {func_name}({args_str}) -> {return_type}:")
                else:
                    signatures.append(f"def {func_name}({args_str}):")
    except Exception as e:
        logger.warning(f"AST parsing failed: {e}")
    
    return "\n".join(signatures) if signatures else ""


def regenerate_tests_with_signature_hint(
    requirement: str,
    sample_io: str,
    code: str,
    failed_tests: list,
    entry_point: str,
    api: str = "api_1"
) -> tuple:
    """Auto-translated documentation for regenerate_tests_with_signature_hint."""
    signature = extract_function_signature(code, entry_point)
    if not signature:
        signature = f"def {entry_point}(...):"
    
    failed_info_parts = []
    for i, result in enumerate(failed_tests):
        full_test_case = result.test_case if hasattr(result, 'test_case') else str(result)
        error_msg = result.error_message if hasattr(result, 'error_message') else ''
        status = result.status.name if hasattr(result, 'status') else 'UNKNOWN'
        failed_info_parts.append(f"""
```python
{full_test_case}
```
Error message: {error_msg}
""")
    failed_info = "\n".join(failed_info_parts)
    
    sample_io_formatted = format_sample_io(sample_io)
    
    prompt = f"""# Role
You are a test-case repair specialist. Analyze why the previous tests failed and generate test cases with the correct format and semantics.

# Example Supremacy
Treat sample I/O and embedded examples as the source of truth.
- Infer the API input and output types from the examples.
- If the text says one type but the examples show another, follow the examples.
- Infer types from notation: `[]` = List, `()` = Tuple, `{{}}` = Dict.

# Use the following function signature to keep the API format correct
```python
{signature}
```
- Ensure the function name, parameter order, types, and import statement are correct.

# Expected-Value Rule
Expected outputs must be computed independently from the problem description, not by assuming the code is correct.

# Black-Box Rule
- Do not use `sys.stdin`, `sys.stdout`, or `io.StringIO` inside the tests.
- Do not implement a reference solution.
- Do not define helper data structures such as Fenwick trees or segment trees inside the tests.
- Use hardcoded expected outputs.
- If a helper is absolutely necessary, it must start with `_`.

# stdin Call Format
For stdin-style problems, call the function directly in the assertion, for example:
- `self.assertEqual(solve(1), 2024)`
- `self.assertEqual(solve("1"), 2024)`
- Do not assign the input to an intermediate variable before calling `solve()`.

# Failed Tests
{failed_info}

# Problem Description
{requirement}

# Sample I/O
{sample_io_formatted}

# Task
1. Diagnose whether the failures come from API usage, type mismatch, or incorrect expected values.
2. Preserve the useful scenario coverage from the failed tests.
3. Fix the calling format and expected values where needed.
4. Add important missing scenarios when necessary.
5. Generate correct tests for `{entry_point}` that cover happy paths, edge cases, and the original failed scenarios.

```python
import unittest
from solution import {entry_point}

class TestSolution(unittest.TestCase):
    pass
```
"""
    
    logger.info(f"Regenerating tests with a signature hint. Signature: {signature}")
    print(f"[regenerate_tests_with_signature_hint] Function signature: {signature}")
    
    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)
    
    print(f"Signature-guided regeneration prompt:\n{prompt}")
    print(f"Signature-guided regeneration output:\n{llm_output}")
    
    new_tests = extract_python_code(llm_output)
    new_tests = sanitize_python_code(new_tests)
    new_tests = remove_non_test_functions(new_tests, entry_point)
    new_tests = remove_comments(new_tests)
    
    logger.info(f"Signature-guided regeneration complete. Generated {count_test_methods(new_tests)} test methods")
    
    return new_tests, prompt_tokens, completion_tokens
