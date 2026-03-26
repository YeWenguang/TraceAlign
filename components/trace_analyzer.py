from llm.client import call_openai_api, call_openai_api2
from utils.extract_code import extract_python_code
from utils.TracePy import ExecutionResult
from typing import List, Union
import logging
logger = logging.getLogger(__name__)
from dataclasses import dataclass
import json
import re
import logging
from typing import List, Dict, Any

MAX_PROMPT_TOKENS = 30000
MAX_TRACE_LOG_LENGTH = 2000

def estimate_tokens(text: str) -> int:
    return len(text) // 4

def truncate_trace_log(trace_log: str, max_length: int = MAX_TRACE_LOG_LENGTH) -> str:
    if len(trace_log) <= max_length:
        return trace_log
    
    lines = trace_log.split('\n')
    if len(lines) <= 50:
        return trace_log[:max_length] + "\n... [TRUNCATED]"
    
    head_lines = lines[:20]
    tail_lines = lines[-30:]
    
    truncated = "\n".join(head_lines)
    truncated += f"\n\n... [{len(lines) - 50} lines omitted] ...\n\n"
    truncated += "\n".join(tail_lines)
    
    return truncated

@dataclass
class JudgeResult:
    test_case: str
    is_correct: bool
    reasoning: str
    error_location: str = ""
    faulty_trace_step: str = ""
    root_cause: str = ""


def get_prompt_analyze_trace(problem_desc: str, code: str, failures: Union[List[ExecutionResult], ExecutionResult]) -> str:
    """Auto-translated documentation for get_prompt_analyze_trace."""
    
    if not isinstance(failures, list):
        failures = [failures]

    failure_evidence_str = ""
    
    for i, f in enumerate(failures):
        truncated_trace = truncate_trace_log(f.trace_log)
        failure_evidence_str += f"""
[Failure Case #{i+1}]
- Status: {f.status} 
- Test Case:\n{f.test_case}
- Error Message: {f.error_message}
- Trace (Last 100 Steps):
```text
{truncated_trace}
```
"""

    Correct_temp = """{
"test_case": "corresponding test case",
"reasoning": "Now I start to simulate the trace line-by-line...",
"is_correct": true
}"""

    Test_Case_Wrong_temp = """{
"test_case": "corresponding test case",
"reasoning": "The TEST CASE EXPECTED VALUE violates problem constraints...",
"is_correct": true,
"root_cause": "TEST_CASE_LOGIC_ERROR: The expected output of the test case contradicts a rule stated in the Problem Description"
}"""

    Incorrect_temp = """{
"test_case": "corresponding test case",
"reasoning": "Now I start to simulate the trace line-by-line...",
"is_correct": false,
"error_location": "e.g., Line 12 (inside the while loop)",
"faulty_trace_step": "Copy the EXACT line from the Trace where the divergence happens (e.g., 'Line 12: count=5 | Vars: {{count=5}}')",
"root_cause": "Explain the logic gap: 'The problem says count should reset at 5, but the code continued incrementing'."
}"""

    num_failures = len(failures)
    
    PROMPT = f"""# Task
Analyze the following failed test cases. Determine if the failure is caused by **BUGGY CODE** (lack of robustness/logic errors) or a **WRONG TEST CASE** (incorrect expectations).

# 🚨 Critical Judgment Rules (Read Carefully)

## 1. When to Blame the Test Case (`is_correct: true`) - CONSERVATIVE APPROACH
Set `is_correct: true` (meaning the code is fine, delete the test) **ONLY IF ALL** of the following conditions are met:
- The **Expected Output** **CLEARLY and EXPLICITLY** violates the problem's mathematical rules stated in the Problem Description (e.g., Problem says "sum of positive integers", test expects "sum including negative numbers").
- The violation is **NOT** about edge cases, boundary conditions, or input validation.
- You can point to a **specific sentence** in the Problem Description that the test case contradicts.

### ❌ DO NOT Blame the Test Case for:
1. **Edge Cases**: Empty strings, empty lists, single elements, boundary values (0, -1, max_int)
2. **Input Validation Tests**: Testing with None, wrong types, malformed inputs
3. **Boundary Conditions**: Testing limits, overflow scenarios
4. **Format Variations**: Different input formats that are still valid (e.g., "CamelCaseString" when function expects snake_case - this tests robustness!)
5. **"Out of Scope" Claims**: Unless the problem **explicitly excludes** certain inputs, assume all reasonable inputs are valid
6. **Runtime Errors**: If the code crashes (IndexError, TypeError, ValueError, etc.), the CODE is at fault for not handling the input gracefully

### ⚠️ Special Rule for Runtime Errors (ERROR status)
If the test case caused a **Runtime Error** (Exception/Crash):
- **DEFAULT**: Blame the CODE (`is_correct: false`) - Robust code should handle edge cases gracefully
- **EXCEPTION**: Only blame the test case if the input is **explicitly forbidden** by the Problem Description with phrases like:
  - "Input is guaranteed to be non-empty"
  - "All inputs will be positive integers"
  - "You can assume the input is always valid"
- **NO explicit guarantee = CODE is at fault**

## 2. When to Blame the Code (`is_correct: false`) - DEFAULT CHOICE
Set `is_correct: false` (meaning the code needs fixing) IF:
- **Runtime Crash (Exception)**: The code raised an unhandled error (e.g., `IndexError`, `ValueError`, `TypeError`, `KeyError`, `AttributeError`) 
  - **Reasoning**: Robust code MUST validate inputs or handle edge cases gracefully (e.g., return `False`, `None`, or `0`), NOT crash.
- **Logic Failure**: The code ran without crashing but returned the wrong result.
- **Timeout**: The code was too slow or had infinite loop.
- **Any Doubt**: When in doubt, blame the code - it's safer to fix code than delete potentially valuable tests.

# Analysis Decision Tree
1. **Did the code Crashor** (Status = ERROR)
   - **YES** -> Does the Problem Description **explicitly guarantee** this input is impossibleor
     - Check for phrases like "guaranteed to be", "always", "will never be", "you can assume"
     - If **explicitly forbidden**: Blame Test Case (`is_correct: true`) with quote from problem.
     - If **no explicit guarantee**: Blame Code (`is_correct: false`) -> **Code lacks input validation.**
2. **Did the code Return Wrong Resultor** (Status = FAIL)
   - **YES** -> Does the Test expectation **clearly contradict** a rule stated in Problem Descriptionor
     - If **clear contradiction with quote**: Blame Test Case.
     - If **edge case / boundary / format variation**: Blame Code.
     - If **uncertain**: Blame Code (conservative approach).

# Input Data
## [Problem Description]
{problem_desc}

## [Code]
```python
{code}
```

## [Failure Evidence]
{failure_evidence_str}

# 📋 Trace Format Guide
The trace logs use the following symbols and structure:
- **⚡** = Critical control flow (if/else/return/break) - ALWAYS examine these first
- **🆕** = First time this line was executed - identifies which branches were taken
- **📝** = Variable value changed since last log - track state changes here
- **`(xN)`** = Line executed N times (e.g., `(x50)` means 50 iterations in a loop)

**Structure**:
- `[TRACE HEAD] (Init Phase)` = First 30 logged lines (initialization)
- `[TRACE TAIL] (Pre-Interrupt)` = Last 120 logged lines - **MOST IMPORTANT for root cause**
- `📍>>> EXECUTION INTERRUPTED HERE <<<` = Where timeout/error occurred

# Output Format
**CRITICAL**: You received **{num_failures} Failure Case(s)** in the input. You MUST return a JSON list containing **EXACTLY {num_failures} objects**, one for each Failure Case.

Example format (for 3 cases - including a wrong test case):
[
  {Correct_temp},
  {Test_Case_Wrong_temp},
  {Incorrect_temp}
]

**WARNING**: If you return fewer than {num_failures} results, your response will be considered INCOMPLETE and will cause system errors. Do NOT skip any Failure Case.

# root_cause Categories
When `is_correct: true` (code is correct, test is wrong), use one of:
- `TEST_CASE_LOGIC_ERROR: <explanation>` - Expected output **clearly violates** a rule stated in Problem Description (quote the rule)
- `TEST_CASE_FORMAT_ERROR: <explanation>` - Input format is **explicitly forbidden** by Problem Description (quote the restriction)
- `PRECISION_MISMATCH: <explanation>` - Floating-point/decimal precision difference

When `is_correct: false` (code has bug), describe the specific bug and what validation is missing.

# Important Rules
1. If the trace shows a **Timeout (TLE)**, the code is automatically **INCORRECT**. 
2. **MUST return {num_failures} JSON objects** - one per Failure Case. Double-check before submitting.
3. **DEFAULT TO FIX_CODE**: When uncertain, always choose `is_correct: false` - it's better to fix code than delete tests.
"""
    return PROMPT


def judge_code_logic(problem_desc, code, target_failures: List[ExecutionResult], api: str = "api_1") -> List[JudgeResult]:
    """Auto-translated documentation for judge_code_logic."""
    if not target_failures:
        return []

    prompt = get_prompt_analyze_trace(problem_desc, code, target_failures)
    
    estimated_tokens = estimate_tokens(prompt)
    if estimated_tokens > MAX_PROMPT_TOKENS:
        print(f"Warning: prompt too long ({estimated_tokens} tokens); processing in batches...")
        return judge_code_logic_batched(problem_desc, code, target_failures, api)
    
    try:        
        if api == "api_1":
            llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt) 
        else:
            llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)
        parsed_list = _parse_json_list_output(llm_output)
        
        results = []
        for item in parsed_list:
            res = JudgeResult(
                test_case=item.get("test_case", ""),
                is_correct=item.get("is_correct", False),
                reasoning=item.get("reasoning", ""),
                error_location=item.get("error_location", ""),
                faulty_trace_step=item.get("faulty_trace_step", ""),
                root_cause=item.get("root_cause", "")
            )
            results.append(res)

        if len(results) < len(target_failures):
            print(f"Warning: the judge returned {len(results)} results, but {len(target_failures)} failing cases were provided!")
            judged_cases = {r.test_case for r in results}
            
            for failure in target_failures:
                is_judged = any(
                    failure.test_case in judged_case or judged_case in failure.test_case 
                    for judged_case in judged_cases
                )
                
                if not is_judged:
                    print(f"   Added fallback decision: {failure.test_case[:50]}... -> FIX_CODE")
                    results.append(JudgeResult(
                        test_case=failure.test_case,
                        is_correct=False,
                        reasoning="Judge did not return result for this case, defaulting to FIX_CODE",
                        error_location="Unknown",
                        faulty_trace_step="",
                        root_cause="Missing judge result - LLM output incomplete"
                    ))

        print(f"judge_code_logic results: {results}")
        return results, prompt_tokens, completion_tokens

    except Exception as e:
        logger.error(f"Judge Error: {e}")
        return [], 0, 0


def judge_code_logic_batched(problem_desc, code, target_failures: List[ExecutionResult], api: str = "api_1") -> List[JudgeResult]:
    """Auto-translated documentation for judge_code_logic_batched."""
    all_results = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    
    batch_size = 1
    for i in range(0, len(target_failures), batch_size):
        batch = target_failures[i:i + batch_size]
        print(f"  Processing batch {i//batch_size + 1}/{(len(target_failures) + batch_size - 1)//batch_size}")
        
        prompt = get_prompt_analyze_trace(problem_desc, code, batch)
        
        try:
            if api == "api_1":
                llm_output, p_tok, c_tok = call_openai_api(prompt)
            else:
                llm_output, p_tok, c_tok = call_openai_api2(prompt)
            
            total_prompt_tokens += p_tok
            total_completion_tokens += c_tok
            
            parsed_list = _parse_json_list_output(llm_output)
            
            for item in parsed_list:
                res = JudgeResult(
                    test_case=item.get("test_case", ""),
                    is_correct=item.get("is_correct", False),
                    reasoning=item.get("reasoning", ""),
                    error_location=item.get("error_location", ""),
                    faulty_trace_step=item.get("faulty_trace_step", ""),
                    root_cause=item.get("root_cause", "")
                )
                all_results.append(res)
                
        except Exception as e:
            logger.error(f"Batch Judge Error: {e}")
            for failure in batch:
                all_results.append(JudgeResult(
                    test_case=failure.test_case,
                    is_correct=False,
                    reasoning=f"Judge API error: {str(e)}",
                    error_location="Unknown",
                    faulty_trace_step="",
                    root_cause="API call failed"
                ))
    
    if len(all_results) < len(target_failures):
        judged_cases = {r.test_case for r in all_results}
        for failure in target_failures:
            is_judged = any(
                failure.test_case in judged_case or judged_case in failure.test_case 
                for judged_case in judged_cases
            )
            if not is_judged:
                all_results.append(JudgeResult(
                    test_case=failure.test_case,
                    is_correct=False,
                    reasoning="Missing result from batched processing",
                    error_location="Unknown",
                    faulty_trace_step="",
                    root_cause="Batch processing incomplete"
                ))
    
    return all_results, total_prompt_tokens, total_completion_tokens

def _extract_field_with_regex(text: str, field: str) -> str:
    """Auto-translated documentation for _extract_field_with_regex."""
    
    
    key_pattern = re.compile(f'[\'"]or{re.escape(field)}[\'"]or\\s*:\\s*', re.IGNORECASE)
    match = key_pattern.search(text)
    
    if not match:
        return ""
    
    value_start_index = match.end()
    remaining = text[value_start_index:].strip()
    
    if not remaining:
        return ""

    first_char = remaining[0]
    if first_char in ['"', "'"]:
        escaped = False
        for i in range(1, len(remaining)):
            char = remaining[i]
            if escaped:
                escaped = False
                continue
            if char == '\\':
                escaped = True
                continue
            if char == first_char:
                return remaining[1:i]
        return ""
    
    match_value = re.match(r'([^,}\s]+)', remaining)
    if match_value:
        return match_value.group(1).strip()
        
    return ""

def extract_json_objects(text: str) -> List[str]:
    """Auto-translated documentation for extract_json_objects."""
    objects = []
    brace_level = 0
    start_index = -1
    in_string = False
    escape = False
    
    for i, char in enumerate(text):
        if in_string:
            if char == '\\':
                escape = not escape
            elif char == '"' and not escape:
                in_string = False
            else:
                escape = False
            continue
            
        if char == '"':
            in_string = True
            continue
            
        if char == '{':
            if brace_level == 0:
                start_index = i
            brace_level += 1
        elif char == '}':
            if brace_level > 0:
                brace_level -= 1
                if brace_level == 0:
                    objects.append(text[start_index:i+1])
                    
    return objects

def _parse_json_list_output(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []

    cleaned_text = re.sub(r"^\s*```(or:json)or\s*|^\s*|```\s*$", "", text.strip(), flags=re.MULTILINE)
    try:
        parsed = json.loads(cleaned_text)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass

    json_strings = extract_json_objects(text)
    results = []

    for obj_str in json_strings:
        try:
            results.append(json.loads(obj_str))
            continue
        except json.JSONDecodeError:
            pass
        
        logger.warning(f"JSON object parse failed, using regex fallback for: {obj_str[:50]}...")
        extracted_item = {}
        
        extracted_item["reasoning"] = _extract_field_with_regex(obj_str, "reasoning")
        extracted_item["test_case"] = _extract_field_with_regex(obj_str, "test_case")
        
        is_correct_match = re.search(r'[\'"]oris_correct[\'"]or\s*:\s*(true|false)', obj_str, re.IGNORECASE)
        extracted_item["is_correct"] = is_correct_match.group(1).lower() == 'true' if is_correct_match else False

        if not extracted_item["is_correct"]:
            extracted_item["error_location"] = _extract_field_with_regex(obj_str, "error_location")
            extracted_item["faulty_trace_step"] = _extract_field_with_regex(obj_str, "faulty_trace_step")
            extracted_item["root_cause"] = _extract_field_with_regex(obj_str, "root_cause")
            
        results.append(extracted_item)

    return results
