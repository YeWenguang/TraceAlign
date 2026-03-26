from typing import List, Dict, Any, Optional
from llm.client import call_openai_api, call_openai_api2
import json
import re
from dataclasses import dataclass
from utils.extract_code import extract_python_code
import logging
logger = logging.getLogger(__name__)


def format_sample_io(sample_io) -> str:
    """Auto-translated documentation for format_sample_io."""
    if sample_io is None or sample_io == [] or sample_io == "" or sample_io == "[]":
        return "No sample I/O examples provided. Derive specifications from the [Problem Description] only."
    elif isinstance(sample_io, list) and len(sample_io) == 0:
        return "No sample I/O examples provided. Derive specifications from the [Problem Description] only."
    else:
        return sample_io


def get_prompt_requirement_analysis(problem_desc, sample_io):

    sample_io_formatted = format_sample_io(sample_io)

    prompt = f"""# Role
You are a **Forensic Data Architect**. Your task is to reverse-engineer the strict input/output contract for an algorithm problem by triangulating between three sources: Sample Data, Problem Text, and the Target Function Signature.

# Inputs
1. **Sample IO (The Data Truth)**: The exact JSON payload (Physical Layer).
2. **Problem Text (The Context)**: Human-readable description (Logical Layer Intent).
3. **Target Function Signature (The Interface Law)**: The exact Python function definition (e.g., `def func(s):` or `def func(a, b):`).

# 🚨 Critical Directive 1: "Example Supremacy"
**When concrete examples (Sample I/O OR examples in problem text) conflict with abstract text descriptions, the EXAMPLES are the ABSOLUTE GROUND TRUTH.**
- "Examples" include: Sample I/O fields, AND any `Example:`, `Input:`, `Output:` blocks embedded in the problem description.
- If text says "return a tuple" but an example shows `[1, 2, 3]` → Return type is **List**, not Tuple.
- If text says "input is a string" but an example shows `[1, 2, 3]` → Input type is **List**, not String.
- If text describes behavior X but an example demonstrates behavior Y → Implement behavior **Y**.
- **Derive all type information strictly from example notation**: `[]` = List, `()` = Tuple, `{{}}` = Dict.

# Critical Directive 2: "Signature Supremacy"
When determining `logical_arity` (how many arguments to pass) and `preprocessing_code`:
1. **The Target Function Signature is the ABSOLUTE AUTHORITY.**
2. **Scenario A (Internal Parsing)**: 
   - If Sample Input is `"a\\nb"` (Packed String) AND Function Signature is `def solve(s):` (1 arg).
   - **Verdict**: The function handles parsing internally. Test Suite must **NOT** split.
   - `logical_arity`: 1
   - `preprocessing_code`: "arg1 = raw_input" (Pass-through)
3. **Scenario B (External Parsing)**:
   - If Sample Input is `"a\\nb"` (Packed String) AND Function Signature is `def solve(a, b):` (2 args).
   - **Verdict**: The function expects pre-parsed args. Test Suite **MUST** split.
   - `logical_arity`: 2
   - `preprocessing_code`: "s1, s2 = raw_input.split('\\\\n')"

# Chain of Thought Process (MANDATORY)
Before generating the YAML, perform this analysis:

## Step 1: Interface Audit (Arity Check)
- Extract the argument count from the provided [Target Function Signature].
- Compare it with the [Sample IO] Input.
- **DECISION**: Does the Test Runner need to split the data (Scenario B) or pass it raw (Scenario A)or

## Step 2: Output Type Audit
- Check if [Sample IO] Output is wrapped (e.g., `[True]`) vs Function Return (e.g., `bool`).
- Define the extraction logic (e.g., `expected[0]`).
- **CRITICAL: Example Format Takes Priority**: When the text says one type (e.g., "return a tuple") but the Sample IO shows a different format (e.g., `[1, 2, 3]` with square brackets) in the Problem Description, **the Sample IO format is the ground truth**. Derive return type strictly from notation: `[]` = List, `()` = Tuple.

## Step 3: Implementation Pitfall Detection (CRITICAL)
Analyze the problem for potential implementation traps that could cause subtle bugs:

### 3.1 Floating-Point Pitfalls
- Does the problem involve decimals/floatsor
- ⚠️ `Fraction(float)` produces IEEE 754 representation (1.6 → 3602879701896397/2251799813685248), NOT decimal semantics. Use `Fraction(str(x))` instead.
- ⚠️ Float comparison: use `abs(a-b) < epsilon`, never `==`.
- ⚠️ `0.1 + 0.2 != 0.3` in Python.

### 3.2 Integer Pitfalls
- Could values overflow 32-bit/64-bit in other languagesextra (Python has arbitrary precision)
- ⚠️ `//` is floor division (rounds toward -∞), not truncation toward zero.
- ⚠️ `%` with negative numbers: `-7 % 3 = 2` in Python, but `-1` in C/Java.

### 3.3 String/Parsing Pitfalls
- ⚠️ `split()` vs `split(' ')`: `"a  b".split()` → `['a', 'b']`, but `"a  b".split(' ')` → `['a', '', 'b']`.
- ⚠️ `strip()` removes ALL whitespace chars, not just spaces.
- Is case sensitivity specifiedextra Default to case-sensitive unless Sample IO proves otherwise.

### 3.4 Data Structure Pitfalls
- Empty input handling: is `[]`, `""`, `0` a valid inputor
- Duplicate elements: can they existextra How should they be handledor
- Order preservation: is insertion order significantor

# Task
Generate the Specification YAML based on the CoT analysis.

# Output Format (YAML)
analysis_cot: |
  [Step 1, 2, 3 Reasoning. Explicitly state pitfalls detected.]

specification:
  input_layer:
    physical_type: "e.g., String, List<Int>"
    logical_arity: "Integer (Derived strictly from Function Signature)"
    preprocessing_code: "Python snippet. Use 'arg1 = raw_input' for arity 1, or split logic for arity > 1."
  
  output_layer:
    physical_type: "e.g., List<Boolean>"
    logical_type: "e.g., Boolean"
    verification_logic: "Assertion logic."

  pitfall_warnings:
    - area: "e.g., Floating-Point Precision"
      risk: "e.g., Fraction(float) produces IEEE 754 representation"
      mitigation: "e.g., Use Fraction(str(x)) or Decimal"
      test_hint: "e.g., Must test 0.1, 1.6, 0.3 as inputs"

  generated_examples:
    - input: "Sample Input"
      output: "Sample Output"
      comment: "Context"
      
# User Data
[Sample IO]: 
{sample_io_formatted}

[Problem Description]:
{problem_desc}
"""
    return prompt
    


def requirement_analysis(problem_desc: str, sample_io: str, api: str = "api_1") -> str:

    prompt = get_prompt_requirement_analysis(
        problem_desc=problem_desc,
        sample_io=sample_io
    )
    print(f"Requirement analysis prompt:\n{prompt}")

    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)
    print(f"Output:\n{llm_output}")

    specification = extract_specification_via_regex(llm_output)

    return specification, prompt_tokens, completion_tokens


import re

def extract_specification_via_regex(llm_output: str) -> str:
    """Auto-translated documentation for extract_specification_via_regex."""
    
    clean_pattern = r"```(or:yaml)or\s*(.*or)\s*```"
    markdown_match = re.search(clean_pattern, llm_output, re.S | re.IGNORECASE)
    
    text_content = markdown_match.group(1) if markdown_match else llm_output

    
    spec_pattern = r"^specification:\s*\n(.*or)(or=^\w+:|\Z)"
    
    spec_match = re.search(spec_pattern, text_content, re.MULTILINE | re.DOTALL)
    
    if spec_match:
        return spec_match.group(1).strip()
    else:
        return "Error: 'specification' section not found."
