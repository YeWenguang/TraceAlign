from llm.client import call_openai_api, call_openai_api2
from utils.extract_code import extract_python_code
import logging
import re
logger = logging.getLogger(__name__)


def get_prompt_code_generation(requirements, entry_point=None, is_stdin_problem=False):
    entry_point_instruction = ""
    if entry_point:
        if isinstance(entry_point, list):
            entry_point_str = entry_point[0] if entry_point else "solve"
        else:
            entry_point_str = entry_point
        entry_point_instruction = f"""
# 🚨 CRITICAL: Function Name Requirement
**The main function MUST be named `{entry_point_str}`.**
- Do NOT use generic names like `solve()` or `main()`.
- The function signature must be: `def {entry_point_str}(...):`
- This is MANDATORY - the test harness will call `{entry_point_str}` directly.
"""
    
    stdin_instruction = ""
    if is_stdin_problem:
        stdin_instruction = f"""
# 🚨 CRITICAL: Standard Input/Output Requirement (LiveCodeBench)
**This problem requires reading from stdin and writing to stdout.**
- You MUST include a complete program with input parsing and output printing.
- **MANDATORY Structure**:
  ```python
  def solve():
      # Read input from stdin
      import sys
      data = sys.stdin.read().strip().split()
      # Parse input according to problem format
      # ... your logic ...
      # Print result
      print(result)
  
  if __name__ == "__main__":
      solve()
  ```
- **Input Parsing Tips**:
  - Use `sys.stdin.read()` for flexible input handling
  - Use `.split()` to split by whitespace
  - Convert types as needed: `int(data[0])`, `list(map(int, data))`
  - For multi-line input, use `sys.stdin.read().strip().split('\\n')`
- **Output**: Always use `print()` to output the result.
"""
    
    boundary_instruction = """
# 🚨 CRITICAL: Edge Case & Boundary Condition Handling
**You MUST handle edge cases explicitly. Common pitfalls:**
1. **Empty inputs**: Check if list/string is empty before accessing elements
2. **Zero values**: Handle `n=0`, `k=0`, empty ranges like `range(0, 0, -1)`
3. **Single element**: Test with arrays of length 1
4. **Boundary values**: Test with min/max values from constraints
5. **Index safety**: Always check `0 <= index < len(array)` before access
6. **Division by zero**: Check denominators before division
7. **Negative numbers**: Handle negative indices and values if allowed

**Example defensive coding**:
```python
# Before accessing list
if not arr:  # Handle empty list
    return default_value
result = arr[0] if len(arr) > 0 else default

# Before range with potential zero
for i in range(max(1, n), 0, -1):  # Ensure at least one iteration if needed

# Before division
if divisor != 0:
    result = numerator / divisor
```
"""
    
    complexity_instruction = """
# 🚨 CRITICAL: Algorithm Complexity Awareness
**Consider time complexity constraints. Common issues:**
1. **Avoid O(N²) for N > 10⁴**: Use hash maps, binary search, or two pointers
2. **Avoid O(answer) iteration**: If answer can be 10⁹, use binary search on answer
3. **Avoid O(N × M) simulation**: If M can be 10¹⁸, use mathematical formulas
4. **Stack/Queue operations**: Avoid repeated list.pop(0) - use collections.deque

**Red flags that suggest algorithm redesign**:
- Nested loops with large bounds
- Simulating step-by-step when answer can be computed directly
- Using heap for each unit when batch processing is possible

**Example: Binary search on answer instead of simulation**
```python
# BAD: O(answer × log N) - too slow for answer up to 10⁹
while remaining > 0:
    cost = heapq.heappop(heap)
    # ... simulate each unit ...

# GOOD: O(log(max_answer) × N) - binary search on answer
def can_achieve(target):
    # Check if target is achievable in O(N)
    pass

lo, hi = 0, max_possible
while lo < hi:
    mid = (lo + hi + 1) // 2
    if can_achieve(mid):
        lo = mid
    else:
        hi = mid - 1
```
"""
    
    prompt_code_generation = f"""# Task
Write Python code to solve the following problem.
{entry_point_instruction}
{stdin_instruction}
# 🚨 Critical Directive: "Example Supremacy"
**When concrete examples conflict with abstract text descriptions, the EXAMPLES are the ABSOLUTE GROUND TRUTH.**
- "Examples" include: Sample I/O fields, AND any `Example:`, `Input:`, `Output:` blocks in the problem description.
- If text says "return a tuple" but an example shows `[1, 2, 3]` → Return type is **List**, not Tuple.
- If text says "input is a string" but an example shows `[1, 2, 3]` → Input type is **List**, not String.
- If text describes behavior X but an example demonstrates behavior Y → Implement behavior **Y**.
- **Derive all type information strictly from example notation**: `[]` = List, `()` = Tuple, `{{}}` = Dict.

{boundary_instruction}
{complexity_instruction}
# Requirements
{requirements}

# Output Format
- Output ONLY the Python code, wrapped in ```python ... ``` code blocks.
- **MANDATORY Code Structure**:
  - The main function name must match the problem requirement (see Function Name Requirement above).
  - The function should accept the required arguments and **RETURN** the result (unless stdin problem).
  - Do NOT print inside the function unless the problem asks to print specific patterns.
  - Helper functions are allowed but the main entry point must have the correct name.
- {"Include the `if __name__ == '__main__':` block for stdin-based problems." if is_stdin_problem else "Do NOT include `if __name__ == '__main__':` block - only the function definitions."}
"""
    logger.info(f"Code generation prompt:\n{prompt_code_generation}")
    return prompt_code_generation


def code_generation(requirements: str, entry_point: str = None, api: str = "api_1", is_stdin_problem: bool = False):
    """Auto-translated documentation for code_generation."""
    logger.info("Starting initial code generation...")
    
    prompt = get_prompt_code_generation(requirements, entry_point, is_stdin_problem)
    
    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)

    print(f"Code generation output:\n{llm_output}")
    
    code = extract_python_code(llm_output, keep_main_block=is_stdin_problem)
    
    if entry_point and code:
        if isinstance(entry_point, list):
            target_name = entry_point[0] if entry_point else None
        else:
            target_name = entry_point
        
        if target_name:
            func_pattern = r'def\s+(\w+)\s*\('
            matches = re.findall(func_pattern, code)
            if matches and 'solve' in matches and target_name not in matches:
                code = re.sub(r'def\s+solve\s*\(', f'def {target_name}(', code)
                print(f"[Auto-rename] Renamed function 'solve' to '{target_name}'")

    print(f"Generated initial code:\n{code}")
    
    
    return code, prompt_tokens, completion_tokens

