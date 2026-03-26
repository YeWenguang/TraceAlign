import logging
import re
from typing import Optional
from llm.client import call_openai_api, call_openai_api2
from utils.extract_code import extract_python_code


logger = logging.getLogger(__name__)


def detect_timeout_pattern(error_msg: str, code: str) -> dict:
    """Auto-translated documentation for detect_timeout_pattern."""
    result = {
        "is_timeout": False,
        "complexity_issue": None,
        "algorithm_suggestion": None
    }
    
    timeout_indicators = ['TIMEOUT', 'Time Limit Exceeded', 'timeout', 'TLE']
    error_upper = error_msg.upper()
    
    for indicator in timeout_indicators:
        if indicator.upper() in error_upper:
            result["is_timeout"] = True
            break
    
    if not result["is_timeout"]:
        return result
    
    complexity_patterns = [
        (
            r'while\s+.*:\s*#.*heap',
            "O(answer x log N) heap simulation",
            "Use binary search on the answer plus direct math instead of step-by-step simulation",
        ),
        (
            r'for\s+\w+\s+in\s+range\s*\(\s*\d+\s*\):\s*for\s+\w+\s+in\s+range',
            "O(N^2) nested loops",
            "Consider a hash map, two pointers, or preprocessing",
        ),
        (
            r'heapq\.(heappop|heappush)',
            "Heap operations inside a loop",
            "If the loop count is large, consider batch processing or a mathematical approach",
        ),
        (
            r'while\s+\w+\s*[><=]=?\s*\d+:',
            "Possible infinite loop or oversized loop",
            "Check loop termination conditions and consider binary search",
        ),
        (
            r'\.pop\s*\(\s*0\s*\)',
            "O(N) removal from the head of a list",
            "Use collections.deque instead of list",
        ),
    ]
    
    for pattern, issue, suggestion in complexity_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            result["complexity_issue"] = issue
            result["algorithm_suggestion"] = suggestion
            break
    
    return result


def get_prompt_code_repairer(problem_desc, code, error_msg, entry_point, is_stdin_problem=False, timeout_analysis=None):
    entry_point_str = entry_point if isinstance(entry_point, str) else (entry_point[0] if entry_point else "solve")
    
    stdin_instruction = ""
    if is_stdin_problem:
        stdin_instruction = """
# 🚨 CRITICAL: stdin/stdout Problem
- The code MUST read input from stdin (sys.stdin or input())
- The code MUST print output to stdout (print())
- Include `if __name__ == "__main__":` block
"""
    
    timeout_instruction = ""
    if timeout_analysis and timeout_analysis.get("is_timeout"):
        complexity_issue = timeout_analysis.get("complexity_issue", "Unknown")
        algorithm_suggestion = timeout_analysis.get("algorithm_suggestion", "")
        timeout_instruction = f"""
# 🚨 CRITICAL: Timeout Detected - Algorithm Redesign Required
**Complexity Issue**: {complexity_issue}
**Suggested Approach**: {algorithm_suggestion}

**Common Algorithm Optimizations**:
1. **Binary Search on Answer**: Instead of simulating step-by-step, binary search on the answer
   - Example: If checking "can we achieve Xor" is O(N), use binary search to find max X in O(N log max)
   
2. **Mathematical Formula**: Replace simulation with direct calculation
   - Example: Instead of heap operations for each unit, compute total cost mathematically
   
3. **Hash Map / Dictionary**: Replace O(N²) lookups with O(1) hash lookups

4. **Two Pointers**: For sorted arrays, use two pointers instead of nested loops

5. **Prefix Sum / Sliding Window**: Precompute cumulative information

**You may need to COMPLETELY REDESIGN the algorithm, not just fix bugs.**
"""
    
    boundary_instruction = """
# 🚨 CRITICAL: Edge Case Handling
When fixing the code, ensure these edge cases are handled:
1. **Empty inputs**: `if not arr:` or `if not s:`
2. **Zero values**: Handle `n=0`, `k=0` explicitly
3. **Single element**: Test with arrays of length 1
4. **Index bounds**: Check `0 <= i < len(arr)` before access
5. **Division by zero**: Check divisor before division
6. **Negative numbers**: Handle if allowed by constraints
"""
    
    PROMPT_CODE_REPAIR = f"""
# Role
You are a Senior Python Developer tasked with fixing a specific bug in a solution.

# Input Data
1. **Problem Description**:
{problem_desc}

2. **Buggy Code**:
```python
{code}
```

3. **Diagnostic Reports**:
{error_msg}

4. **Target Function Name**:
`{entry_point_str}`
{stdin_instruction}
{timeout_instruction}
{boundary_instruction}
# Instructions
  1. **Check Function Name (CRITICAL - DO THIS FIRST)**:
     * If the error is `NameError: name 'xxx' is not defined`, check if the function name in the code matches the Target Function Name.
     * If the code defines `def solve(...)` but tests call `{entry_point_str}(...)`, you MUST rename the function to `{entry_point_str}`.
     * **Example**: If code has `def solve(n):` but Target is `is_not_prime`, change to `def is_not_prime(n):`
  
  2. **Analyze Diagnostics**: Carefully examine the Diagnostic Reports. Pay special attention to `TypeError` or errors indicating "missing 1 required positional argument".
  
  3. **Fix Interface Mismatch**: 
     * **Constraint**: You CANNOT change the Test Harness/Caller. You MUST modify the Target Function to accommodate the input format shown in the error trace.
     * **Implementation Strategy**: If the test calls the function with a single raw string (containing `\n`) but the function expects two arguments:
         * Update the function signature to make the second argument optional (e.g., `def func(s1, s2=None):`).
         * Add logic at the top of the function: If `s2` is `None`, split `s1` using the newline character (`s1.split('\n')`) to extract the correct parameters.
  
  4. **Verify Logic**: Once the input is correctly parsed, ensure the core algorithm satisfies the `Problem Description`. Fix any logical bugs within the `Buggy Code`.
  
  5. **Handle Edge Cases**: Add defensive checks for empty inputs, zero values, and boundary conditions.

# Output Format:
Think step by step:
```text
Thinking Step by Step
```

Repaired Code (main function MUST be named `{entry_point_str}`):
```python
# Your fixed Python code here, nothing else
```
"""
    return PROMPT_CODE_REPAIR


def get_prompt_code_repaired_with_trace(problem_desc, code, error_msg, entry_point=None, is_stdin_problem=False, timeout_analysis=None):
    entry_point_str = ""
    if entry_point:
        entry_point_str = entry_point if isinstance(entry_point, str) else (entry_point[0] if entry_point else "")
    
    function_name_instruction = ""
    if entry_point_str:
        function_name_instruction = f"""
# 🚨 Function Name Check (CRITICAL - DO THIS FIRST)
**Target Function Name**: `{entry_point_str}`
- If the error is `NameError: name 'xxx' is not defined`, the function name in your code does NOT match the target.
- If your code has `def solve(...)` but tests call `{entry_point_str}(...)`, you MUST rename the function to `{entry_point_str}`.
- **Example**: `def solve(n):` → `def {entry_point_str}(n):`
"""
    
    stdin_instruction = ""
    if is_stdin_problem:
        stdin_instruction = """
# 🚨 CRITICAL: stdin/stdout Problem
- The code MUST read input from stdin (sys.stdin or input())
- The code MUST print output to stdout (print())
- Include `if __name__ == "__main__":` block
"""
    
    timeout_instruction = ""
    if timeout_analysis and timeout_analysis.get("is_timeout"):
        complexity_issue = timeout_analysis.get("complexity_issue", "Unknown")
        algorithm_suggestion = timeout_analysis.get("algorithm_suggestion", "")
        timeout_instruction = f"""
# 🚨 CRITICAL: Timeout Detected - Algorithm Redesign Required
**Complexity Issue**: {complexity_issue}
**Suggested Approach**: {algorithm_suggestion}

**You may need to COMPLETELY REDESIGN the algorithm, not just fix bugs.**
"""
    
    PROMPT_CODE_REPAIR = f"""# Role
You are a Python Bug-Fixing Expert. Your goal is to diagnose and fix bugs.

# Input
## Problem Description
{problem_desc}

## Buggy Code
```python
{code}
```

## Error Information
{error_msg}
{function_name_instruction}
{stdin_instruction}
{timeout_instruction}
# 📋 Trace Format Guide
The trace logs use the following symbols and structure:
- **⚡** = Critical control flow (if/else/return/break) - ALWAYS examine these
- **🆕** = First time this line was executed - important for identifying which branches were taken
- **📝** = Variable value changed - track state changes here
- **`(xN)`** = Line executed N times (e.g., `(x50)` means 50 iterations)

**Structure**:
- `[TRACE HEAD]` = Initialization phase (first 30 lines)
- `[TRACE TAIL]` = Pre-interruption phase (last 120 lines) - **MOST IMPORTANT for finding bugs**
- `📍>>> EXECUTION INTERRUPTED HERE <<<` = Where timeout/error occurred

# Chain of Thought (Follow ALL 6 steps)

## Step 1: Problem Analysis (2-3 sentences)
- What is the function's goalor
- What are the key constraints and edge casesor

## Step 2: Code Logic Explanation (bullet points)
- Briefly explain the main algorithm/approach
- Identify critical control flow (loops, conditions, recursion)
- **If timeout detected**: Analyze the time complexity

## Step 3: Trace Analysis (line-by-line)
- For the **failed test case**, trace the execution step by step
- Mark where the variable state **diverges** from expectation
- Format: `Line X: variable = value → Expected: Y, Actual: Z`

## Step 4: Comparative Analysis (CRITICAL)
Compare **failed** vs **successful** test cases:
| Aspect | Failed Case | Successful Case |
|--------|-------------|-----------------|
| Input  | extra           | extra               |
| Output | extra           | extra               |
| Key Difference | extra | |

**Question to answer**: What structural difference in inputs causes the code to failor

## Step 5: Error Localization
- **Root Cause**: [1 sentence explaining WHY the bug occurs]
- **Faulty Line(s)**: Line X - [brief description of what's wrong]
- **Error Type**: [ ] Edge Case [ ] Logic Error [ ] Algorithm Flaw [ ] Type Error [ ] NameError (Function Name Mismatch) [ ] Timeout (Complexity Issue)

## Step 6: Fixed Code
```python
# Your fixed code here
```

# CRITICAL RULES
1. **If function name doesn't match the target, RENAME IT FIRST**
2. Keep the function signature unchanged (except for the name if needed)
3. Preserve all working functionality
4. Add comments only for the fixed lines
5. **Handle edge cases**: Empty inputs, zero values, boundary conditions
"""
    return PROMPT_CODE_REPAIR


def repair_code_with_diagnosis(problem_desc, code, confirmed_bugs, entry_point, api: str = "api_1", is_stdin_problem: bool = False):
    """Auto-translated documentation for repair_code_with_diagnosis."""
    
    diagnosis_report_str = ""
    has_timeout = False

    for i, (judge_res, fail_case) in enumerate(confirmed_bugs):
        
        case_content = getattr(fail_case, 'test_case', str(fail_case))
        error_msg = getattr(fail_case, 'error_message', 'No error message')
        status = getattr(fail_case, 'status', 'Unknown')
        
        status_str = str(status).upper()
        if 'TIMEOUT' in status_str or 'TLE' in status_str:
            has_timeout = True
        
        diagnosis_report_str += f"""
[Bug #{i+1}]
- Failed Test Case: 
{case_content}
- Status: {status}
- Error Message: {error_msg}
- Error Location: {judge_res.error_location}
- Root Cause: {judge_res.root_cause}
- Faulty Trace Step: {judge_res.faulty_trace_step}
--------------------------------------------------
"""

    timeout_analysis = None
    if has_timeout:
        timeout_analysis = detect_timeout_pattern(diagnosis_report_str, code)
        if timeout_analysis["is_timeout"]:
            print(f"Warning: timeout issue detected: {timeout_analysis['complexity_issue']}")
            print(f"   Suggested fix: {timeout_analysis['algorithm_suggestion']}")

    prompt = get_prompt_code_repairer(
        problem_desc=problem_desc,
        code=code,
        error_msg=diagnosis_report_str,
        entry_point=entry_point,
        is_stdin_problem=is_stdin_problem,
        timeout_analysis=timeout_analysis
    )

    try:
        if api == "api_1":
            llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
        else:
            llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)
        print(f"Code repair prompt:\n{prompt}")
        print(f"Code repair output:\n{llm_output}")
        
        fixed_code = extract_python_code(llm_output)
        
        if not fixed_code:
            return code, prompt_tokens, completion_tokens
            
        return fixed_code, prompt_tokens, completion_tokens
    except Exception as e:
        return code, prompt_tokens, completion_tokens



def repair_code_with_trace(problem_desc, code, err_msg, entry_point=None, api: str = "api_1", is_stdin_problem: bool = False):
    timeout_analysis = detect_timeout_pattern(err_msg, code)
    if timeout_analysis["is_timeout"]:
        print(f"Warning: timeout issue detected: {timeout_analysis['complexity_issue']}")
        print(f"   Suggested fix: {timeout_analysis['algorithm_suggestion']}")
    
    prompt = get_prompt_code_repaired_with_trace(
        problem_desc=problem_desc,
        code=code,
        error_msg=err_msg,
        entry_point=entry_point,
        is_stdin_problem=is_stdin_problem,
        timeout_analysis=timeout_analysis
    )

    print(f"Code repair prompt:\n{prompt}")

    try:
        if api == "api_1":
            llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
        else:
            llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)
        print(f"Code repair output:\n{llm_output}")

        fixed_code = extract_python_code(llm_output)

        if not fixed_code:
            return code, prompt_tokens, completion_tokens

        return fixed_code, prompt_tokens, completion_tokens
    except Exception as e:
        return code, prompt_tokens, completion_tokens
