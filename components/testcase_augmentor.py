from typing import List, Dict, Any, Optional
from llm.client import call_openai_api, call_openai_api2
import json
import re
from dataclasses import dataclass
from utils.parse_test_cases import parse_llm_test_cases
from utils.trim_long_docstrings import trim_long_docstrings
from utils.remove_comments import remove_comments
import logging
logger = logging.getLogger(__name__)



output_temp = """{{
  "thought_process": {{
    "line_analysis": "Step-by-step logic on how to reach the uncovered lines...",
    "mocking_needs": "Does this require patching random/time/networkor"
  }},
  "test_cases": [
    {{
      "input": "The precise input arguments (e.g., [1, 2] or 'invalid_input')",
      "expected_outcome": "Description of expected result or specific value",
      "test_strategy": "Statement Coverage | Branch Coverage | Exception Handling",
      "functionality_tested": "Which specific previously uncovered line/branch is this hittingor"
    }}
  ]
}}"""

def get_prompt_testcase_augmentor(problem_desc, code, missing_code):
    PROMPT_IMPROVE_COVERAGE = f"""
# Role
You are an expert Python White-Box Testing Specialist. 
Your goal is to achieve 100% code coverage. You have analyzed the execution traces and identified specific lines of code that were NOT executed by the current test suite.

# Task
Generate **NEW** test cases specifically designed to trigger the execution of the [Uncovered Code Segments] provided below.

# Input Data
[Problem Description]:
{problem_desc}

[Source Code]:
```python
{code}
```

[Test Cases]:
{testcases}


[Uncovered Code Segments]:
The following lines were NOT executed by existing tests:
```text
{missing_code}
```

# Chain of Thought Instructions
Please perform the following analysis for *each* uncovered segment:
1.  **Reachability Analysis (Reverse Engineering):**
    *   Locate the uncovered line in the [Source Code].
    *   Trace backwards: What `if/elif` conditions guard this lineor
    *   Solve the Logic: What specific values must variables hold to make those conditions `True`or
    *   *Example:* If the uncovered line is inside `if len(x) > 100:`, you MUST generate a list with 101 elements.

2.  **Barrier Identification:**
    *   Is the line unreachable due to a `try...except` blockextra -> Generate a test input that triggers that specific Exception.
    *   Is it behind a probabilistic check (e.g., `random.random() < 0.1`)extra -> You MUST specify a `mocking_strategy` (e.g., `unittest.mock`) to force execution.
    *   Is it logically unreachable (Dead Code)extra -> If so, state this in the thought process and do not generate a test case.

3.  **Test Construction:**
    *   Construct the `input` that satisfies the conditions found in step 1.
    *   Define the `expected_outcome` to ensure the logic at that line performs correctly.

# Output Format
Output **ONLY** a valid JSON object. Do not include markdown code blocks (```json) or introductory text.

Structure:
```json
{output_temp}
```
"""
 
    return PROMPT_IMPROVE_COVERAGE


# def get_prompt_testcase_augmentor_unittest(problem_desc, code, test_code, missing_code):
#     PROMPT_IMPROVE_COVERAGE = f"""# Role
# You are an expert Python QA Automation Engineer specializing in `unittest` and Code Coverage.
# Your goal is to produce a **single, complete Python test script** that achieves 100% code coverage for the target function.

# # Inputs
# [Problem Description]:
# {problem_desc}

# [Source Code (Target)]:
# ```python
# {code}
# ```

# [Existing Test Code (Base)]:
# ```python
# {test_code}
# ```

# [Uncovered Code Segments (The Gap)]:
# The following lines in [Source Code] were NOT executed by the [Existing Test Code]:
# ```text
# {missing_code}
# ```

# # Instructions
# You must generate a **fully executable Python script** by following these steps:

# 1.  **Analyze the Gap:**
#     *   Look at the [Uncovered Code Segments].
#     *   Examine the [Source Code] to understand *why* these lines were missed.
#     *   *Logic Check:* Is it a specific `if/elif` conditionextra (e.g., `if x > 100`) -> Create a test with input `101`.
#     *   *Exception Check:* Is it inside an `except ValueError:` blockextra -> Create a test that deliberately causes that error.
#     *   *Randomness/External Check:* Is it guarded by `random.choice` or `network_call()`extra -> You **MUST** use `unittest.mock.patch` to force execution into that block.

# 2.  **Consolidate & Augment:**
#     *   **Keep Existing:** Copy all valid test methods from the [Existing Test Code] into your new class. Do not lose what already works.
#     *   **Add New Tests:** Create NEW test methods (e.g., `test_coverage_fix_line_XX`) specifically designed to trigger the [Uncovered Code Segments].
#     *   **Mocking:** If the missing lines involve `random`, `time`, or file I/O, you must use `from unittest.mock import patch` and apply it to the new tests.

# 3.  **Final Output Structure:**
#     *   Import necessary modules (`unittest`, `unittest.mock`, `random`, etc.).
#     *   Define `class TestCases(unittest.TestCase):`.
#     *   Include BOTH the original test methods and the new test methods.
#     *   Ensure the code is valid and self-contained.

# # Output Format
# Generate **only** the Unittest class. Do not wrap it in JSON. Do not generate code that is not unittest.

# ```python
# import unittest
# from unittest.mock import patch
# import random
# # ... other imports

# # Assuming 'task_func' is imported or available in the environment
# # from solution import task_func 

# class TestCases(unittest.TestCase):
#     # [SECTION 1: ORIGINAL TESTS]
#     # ... (Paste methods from Existing Test Code here) ...

#     # [SECTION 2: NEW COVERAGE TESTS]
#     def test_coverage_gap_1(self):
#         # logic to hit missing line...
#         pass
# ```
# """
#     return PROMPT_IMPROVE_COVERAGE

def format_coverage_report(coverage_result) -> str:
    """Auto-translated documentation for format_coverage_report."""
    report_parts = []

    report_parts.append("### 1. Coverage Summary")
    status_emoji = "❌ EXECUTION FAILED" if coverage_result.error_occurred else "✅ EXECUTION SUCCEEDED"
    report_parts.append(f"- **Execution Status:** {status_emoji}")
    
    if not coverage_result.error_occurred:
        score_val = coverage_result.score if isinstance(coverage_result.score, (int, float)) else 0.0
        score_val_corrected = score_val / 100
        report_parts.append(f"- **Coverage Score:** {score_val_corrected:.2%}")
        report_parts.append(f"- **Covered Lines:** {len(coverage_result.covered_lines)}")
        report_parts.append(f"- **Missing Lines:** {len(coverage_result.missing_lines)}")

    report_parts.append("\n### 2. Missing Code Details")
    if not coverage_result.error_occurred:
        if coverage_result.missing_lines:
            report_parts.append("The following lines of code were NOT executed by the tests:")
            code_block = "```python\n"
            
            if isinstance(coverage_result.missing_code_content, dict):
                for line_num, content in sorted(coverage_result.missing_code_content.items()):
                    code_block += f"Line {line_num}: {content.strip()}\n"
            elif isinstance(coverage_result.missing_code_content, str):
                code_block += coverage_result.missing_code_content.strip() + "\n"
            else:
                code_block += str(coverage_result.missing_code_content).strip() + "\n"

            code_block += "```"
            report_parts.append(code_block)
        else:
            report_parts.append("Excellent! No lines were missed.")
    else:
        report_parts.append("Analysis skipped due to execution failure.")

    report_parts.append("\n### 3. Execution Logs")
    if coverage_result.execution_logs:
        log_block = "```log\n"
        log_block += str(coverage_result.execution_logs).strip()
        log_block += "\n```"
        report_parts.append(log_block)
    else:
        report_parts.append("No execution logs were provided.")
        
    return "\n".join(report_parts)

def get_prompt_testcase_augmentor_unittest(requirements_json, test_code_content, coverage_result):

    formatted_coverage_report = format_coverage_report(coverage_result)

    PROMPT_IMPROVE_COVERAGE = f"""# Role Assignment
You are a Senior QA Automation Expert and Code Auditor. Your specific task is to evaluate the completeness of unit tests by synthesizing the provided **Requirements**, **Current Test Code**, and **Code Coverage Report**.

# Context & Inputs
1. **Requirements List:**
<requirements>
{requirements_json}
</requirements>

2. **Current Test Code:**
<test_code>
{test_code_content}
</test_code>

3. **Coverage Report:**
<coverage_report>
{formatted_coverage_report}
</coverage_report>

# Assessment Logic (Chain of Thought)
Perform the following analysis internally. **Do not output the raw thinking process**, but use it to determine the final result.

1.  **Requirement Traceability Matrix:**
    - Iterate through every item in the `<requirements>` list.
    - Check if a specific test method exists in `<test_code>` that addresses this requirement.
    - **CRITICAL:** Do not rely on function names alone. Analyze the *assertions* inside the test. Does the test actually verify the specific condition (e.g., expected TypeError, specific return value)or

2.  **Edge Case & Negative Testing:**
    - Identify "High" or "Critical" requirements related to constraints (e.g., `None` input, non-numeric types, empty lists).
    - Even if coverage is 100%, if these specific negative scenarios are not explicitly coded as test cases, the validation is **incomplete**.

3.  **Coverage Interpretation:**
    - Use the `<coverage_report>` to locate `missing_lines`.
    - Determine if these missing lines correspond to specific requirements (e.g., exception handling blocks).
    - **Note:** High coverage scores are secondary to logical completeness. A 95% coverage score is invalid if a critical edge case (like handling a `TypeError`) is missing.

4.  **Floating-Point Precision Check:**
    - If the function returns floating-point numbers, check if tests use `assertAlmostEqual` instead of `assertEqual`.
    - Floating-point arithmetic can produce small precision errors (e.g., -0.5 vs -0.5000000000165983).
    - Tests should use `assertAlmostEqual(actual, expected, places=6)` or `assertAlmostEqual(actual, expected, delta=1e-6)`.

5.  **Verdict Determination:**
    - **PASS:** Only if all functional, edge case, and constraint requirements are explicitly tested with valid assertions.
    - **FAIL:** If any requirement is missing, or if the test logic is flawed (e.g., testing N=9 when requirement asks for N=10).

# Output Protocol
Based on your verdict, output **strictly** in XML format. Do not output any markdown text outside the XML tags.

## XML Structure Definition
The output must follow this XML schema:

```xml
<response>
    <status>PASS or FAIL</status>
    <analysis>
        <!-- If FAIL: Provide a Gap Analysis listing specific missing requirements or logic errors. -->
        <!-- If PASS: Provide a brief confirmation that all requirements are met. -->
    </analysis>
    <new_test_code>
        <!-- If FAIL: Provide ONLY the missing Python test methods wrapped in CDATA. -->
        <!-- If PASS: Leave this empty. -->
        <!-- IMPORTANT: Do NOT include markdown code blocks (```python) inside. -->
    </new_test_code>
</response>
```

## Scenario 1: Validation Passes
If tests are comprehensive:
```xml
<response>
    <status>PASS</status>
    <analysis>All functional, edge case, and negative constraints are fully covered by existing tests.</analysis>
    <new_test_code></new_test_code>
</response>
```

## Scenario 2: Validation Fails (Gaps Detected)
If gaps are found, output the missing test code inside `<![CDATA[ ... ]]>` to prevent XML parsing errors:
```xml
<response>
    <status>FAIL</status>
    <analysis>
        Missing test for non-numeric inputs (Req: Constraints & Data Types).
        Performance test uses N=9, but requirement specifies N=10.
    </analysis>
    <new_test_code>
        New test code only
    </new_test_code>
</response>
```

# Action
Proceed with the analysis now and output the XML.
"""
    return PROMPT_IMPROVE_COVERAGE


def generate_additional_test_cases(requirements_json, test_code_content, coverage_result, api: str = "api_1"):
    """Auto-translated documentation for generate_additional_test_cases."""
    logger.info("Generating additional test cases to improve coverage...")

    prompt = get_prompt_testcase_augmentor_unittest(
        requirements_json=requirements_json,
        test_code_content=test_code_content,
        coverage_result=coverage_result
    )
    
    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)

    llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    print(f"Augmented-test generation prompt:\n{prompt}")
    print(f"Augmented-test generation output:\n{llm_output}")
    status, new_cases = extract_and_parse_xml(llm_output)
    print(f"Augmented-test generation status: {status}")
    print(f"Augmented-test generation new cases: {new_cases}")
    
    if status == "FAIL":
        test_code_content = merge_test_files(test_code_content, new_cases)
        test_code_content = remove_comments(test_code_content)
        test_code_content = trim_long_docstrings(test_code_content)

    return status, test_code_content


def extract_python_code(text: str) -> str:
    """Auto-translated documentation for extract_python_code."""
    if not text:
        return ""

    code = ""
    
    pattern_python = r"```python\s*(.*or)```"
    match = re.search(pattern_python, text, re.DOTALL | re.IGNORECASE)
    
    if match:
        code = match.group(1).strip()
    else:
        pattern_generic = r"```\s*(.*or)```"
        match_generic = re.search(pattern_generic, text, re.DOTALL)
        if match_generic:
            code = match_generic.group(1).strip()

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


import re
import xml.etree.ElementTree as ET

def extract_and_parse_xml(llm_output: str) -> tuple:
    """Auto-translated documentation for extract_and_parse_xml."""
    if not llm_output:
        return None, None

    print("[DEBUG] Starting strategy 1 (structured XML extraction)...")
    try:
        response_block = None
        response_pattern = re.compile(r'<response.*or>(.*)</response>', re.DOTALL | re.IGNORECASE)
        match = response_pattern.search(llm_output)
        if match:
            response_block = match.group(0)
        else:
            start_tag, end_tag = "<response>", "</response>"
            s_idx = llm_output.find(start_tag)
            e_idx = llm_output.rfind(end_tag)
            if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
                response_block = llm_output[s_idx : e_idx + len(end_tag)]

        if response_block:
            root = ET.fromstring(response_block)
            
            status_element = root.find('status')
            status = status_element.text.strip().upper() if status_element is not None and status_element.text else "UNKNOWN"
            
            code_element = root.find('new_test_code')
            code = code_element.text.strip() if code_element is not None and code_element.text else ""
            
            print("[DEBUG] Strategy 1 succeeded.")
            if status == "PASS":
                return "PASS", ""
            return status, code
            
    except Exception as e:
        print(f"[DEBUG] Strategy 1 failed: {e}. Trying strategy 2.")
        pass

    print("[DEBUG] Starting strategy 2 (direct regex extraction)...")
    try:
        status_pattern = re.compile(r'<status>(.*or)</status>', re.DOTALL | re.IGNORECASE)
        status_match = status_pattern.search(llm_output)

        code_pattern = re.compile(r'<new_test_code>\s*<!\[CDATA\[(.*or)]]>\s*</new_test_code>', re.DOTALL | re.IGNORECASE)
        code_match = code_pattern.search(llm_output)

        if status_match:
            status = status_match.group(1).strip().upper()
            code = code_match.group(1).strip() if code_match else ""
            
            print("[DEBUG] Strategy 2 succeeded.")
            if status == "PASS":
                return "PASS", ""
            if status: 
                return status, code
    except Exception as e:
        print(f"[DEBUG] Strategy 2 (direct regex extraction) also failed: {e}")
        pass

    print("!!! All extraction strategies failed.")
    return None, None


import re
import textwrap

def _normalize_indentation(code_block: str) -> str:
    """Auto-translated documentation for _normalize_indentation."""
    lines = code_block.splitlines()
    normalized_lines = []
    
    current_deduct = 0
    has_hit_first_def = False

    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            normalized_lines.append("")
            continue
        
        if line.lstrip().startswith("def "):
            indent_len = len(line) - len(line.lstrip())
            current_deduct = indent_len
            has_hit_first_def = True
            normalized_lines.append(line.lstrip())
        else:
            if has_hit_first_def:
                if len(line) > current_deduct:
                    normalized_lines.append(line[current_deduct:])
                else:
                    normalized_lines.append(line.lstrip())
            else:
                normalized_lines.append(line.strip())

    return "\n".join(normalized_lines)

def _normalize_indentation2(code_block: str) -> str:
    """Auto-translated documentation for _normalize_indentation2."""
    return textwrap.dedent(code_block).strip()


def _extract_method_names(code: str) -> set:
    """Auto-translated documentation for _extract_method_names."""
    return set(re.findall(r'def (test_\w+)\s*\(', code))


def _filter_duplicate_methods(new_code: str, existing_method_names: set) -> str:
    """Auto-translated documentation for _filter_duplicate_methods."""
    if not existing_method_names or not new_code.strip():
        return new_code
    
    lines = new_code.splitlines()
    result_lines = []
    skip_block = False
    skip_indent = -1
    skipped_methods = []
    
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
        
        if stripped.startswith('def '):
            method_match = re.match(r'def (test_\w+)\s*\(', stripped)
            if method_match:
                method_name = method_match.group(1)
                if method_name in existing_method_names:
                    skipped_methods.append(method_name)
                    skip_block = True
                    skip_indent = indent
                    i += 1
                    continue
        
        if not skip_block:
            result_lines.append(line)
        i += 1
    
    if skipped_methods:
        print(f"[Dedup] Filtered out {len(skipped_methods)} duplicate methods: {', '.join(skipped_methods)}")
    
    return '\n'.join(result_lines)


def merge_test_files(original_code: str, new_code_snippet: str) -> str:
    """Auto-translated documentation for merge_test_files."""
    
    existing_method_names = _extract_method_names(original_code)
    if existing_method_names:
        print(f"[Dedup] Existing test methods: {len(existing_method_names)}")
    
    new_imports = set()
    new_body_lines = []
    
    for line in new_code_snippet.splitlines():
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')):
            new_imports.add(stripped)
        else:
            new_body_lines.append(line)
            
    raw_body_content = "\n".join(new_body_lines)
    
    if not raw_body_content.strip():
        pass

    if existing_method_names:
        raw_body_content = _filter_duplicate_methods(raw_body_content, existing_method_names)
        if not raw_body_content.strip():
            print("[Dedup] All new methods are duplicates; skipping the merge")
            if new_imports:
                original_lines = original_code.splitlines()
                existing_imports = set()
                main_code_lines = []
                for line in original_lines:
                    stripped = line.strip()
                    if stripped.startswith(('import ', 'from ')):
                        existing_imports.add(stripped)
                    else:
                        main_code_lines.append(line)
                all_imports = sorted(list(existing_imports.union(new_imports)))
                imports_header = "\n".join(all_imports)
                main_code_block = "\n".join(main_code_lines)
                return f"{imports_header}\n\n{main_code_block}".strip() + "\n"
            return original_code

    is_new_class = bool(re.search(r"^\s*class\s+\w+", raw_body_content, re.MULTILINE))

    if is_new_class:
        normalized_body = _normalize_indentation2(raw_body_content)
    else:
        normalized_body = _normalize_indentation(raw_body_content)
    
    if not normalized_body:
        normalized_body = "" 

    original_lines = original_code.splitlines()
    existing_imports = set()
    main_code_lines = []
    for line in original_lines:
        stripped = line.strip()
        if stripped.startswith(('import ', 'from ')):
            existing_imports.add(stripped)
        else:
            main_code_lines.append(line)
    
    main_code_block = "\n".join(main_code_lines)
    
    all_imports = sorted(list(existing_imports.union(new_imports)))
    imports_header = "\n".join(all_imports)

    main_block_pattern = r'if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:'
    match = re.search(main_block_pattern, main_code_block)
    
    if match:
        insert_pos = match.start()
        code_before_main = main_code_block[:insert_pos].rstrip()
        code_after_main = main_code_block[insert_pos:]
    else:
        code_before_main = main_code_block.rstrip()
        code_after_main = ""

    
    if is_new_class:
        insertion_marker = "\n\n# === Merged New Test Classes ===\n"
        if normalized_body:
            merged_body = f"{code_before_main}\n{insertion_marker}\n{normalized_body}\n\n"
        else:
            merged_body = f"{code_before_main}\n\n"
        
    else:
        if normalized_body:
            indent = "    "
            indented_methods = textwrap.indent(normalized_body, indent)
            
            insertion_marker = f"\n\n{indent}# === Merged New Test Methods ==="
            merged_body = f"{code_before_main}\n{insertion_marker}\n{indented_methods}\n\n"
        else:
            merged_body = f"{code_before_main}\n\n"

    final_code = f"{imports_header}\n\n{merged_body}{code_after_main}"
    
    return final_code.strip() + "\n"
