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
        return "No sample test cases provided. Analyze the [Problem Description] to derive test scenarios."
    elif isinstance(sample_io, list) and len(sample_io) == 0:
        return "No sample test cases provided. Analyze the [Problem Description] to derive test scenarios."
    else:
        return sample_io


def get_prompt_requirement_extraction1(problem_desc, input_output):

    input_output_formatted = format_sample_io(input_output)

    temp_requirement = """{
  "_analysis_trace": {
    "1_io_protocol_audit": "Compare Problem Text vs Sample IO. Explicitly state the strict input/output types...",
    "2_domain_analysis": "Identify variables and constraints. CRITICAL: Distinguish between EXPLICIT (written) and IMPLIED (assumed) constraints.",
    "3_equivalence_partitioning": "List Valid Equivalence Classes (e.g., positive numbers) and Invalid Equivalence Classes (e.g., negative numbers, non-integers).",
    "4_boundary_value_analysis": "Identify strict boundaries. If input is 1..100, boundaries are 0, 1, 100, 101. Do not hallucinate limits if not stated.",
    "5_complexity_risk": "Deduce Time/Space complexity risks..."
  },
  "scenario_list": [
    {
      "id": "SCN_001",
      "category": "Happy Path | Boundary Value | Edge Case | Negative Test | Performance | Logic Conflict",
      "description": "Abstract description...",
      "test_strategy": "Explain WHY this test is needed (e.g., 'Verifies recursion depth limit').",
      "verification_goal": "What exactly are we verifyingor...",
      "importance": "Critical | High | Medium | Low"
    }
  ]
}"""

    PROMPT_REQUIREMENT_EXTRACTION = f"""# Role
You are a Distinguished Software Test Architect specialized in "Grey Box Testing" and "Combinatorial Testing." You are rigorous, skeptical, and systematic.

# Task
Analyze the provided [Problem Description] and [Sample Testcase] to generate a **MECE (Mutually Exclusive, Collectively Exhaustive)** Test Scenario Checklist.

# 🚨 Critical Directive 1: "Analysis Methodology"
You must apply formal testing techniques in your `_analysis_trace`:
1. **Equivalence Partitioning (EP)**: Group inputs into classes where the system handles them similarly. Generate ONE representative test per class to avoid repetition.
2. **Boundary Value Analysis (BVA)**: Focus on the edges of partitions (min, max, min-1, max+1). Most bugs hide here.
3. **Bug Hunter Mindset**: Anticipate likely developer errors (e.g., Off-by-one errors, Integer overflow, Shallow copy vs Deep copy, Recursion limits).

# 🚨 Critical Directive 2: "Anti-Repetition Protocol" (Orthogonality)
**Do NOT generate redundant scenarios.**
- If Scenario A tests "Input = 5" and Scenario B tests "Input = 6", and both are "middle valid values", **MERGE THEM**.
- **Rule**: Distinct scenarios must trigger **distinct code paths** or verify **distinct logic rules**.
- Avoid "Cookie Cutter" tests: Do not create separate scenarios for "List with 2 items", "List with 3 items", "List with 4 items" unless the problem specifically treats them differently.

# 🚨 Critical Directive 3: "Anti-Hallucination Protocol"
1. **No Magic Numbers**: Do NOT invent mathematical bounds (e.g., "Max Int") unless explicitly written in [Problem Description].
2. **Abstract Definitions**: If a limit is unknown, define the test abstractly (e.g., "Test with a very large input to check TLE" rather than "Test with input size 10^9").
3. **Fact Checking**: If the problem involves complex math (e.g., Primes), verify the property, not the hardcoded value.

# Instructions
1. **Examples are Authority**: Strictly follow code snippets in `Examples` for Input/Output Types. Ignore list wrappers in [Sample Testcase] if they conflict with text examples.
2. **Deep Analysis**: Use the `_analysis_trace` to explicitly list your partitions and boundaries BEFORE generating scenarios.
3. **Full Coverage**:
   - **Functional**: Standard logic.
   - **Edge Cases**: Empty, Null, Single Element, Max/Min Elements.
   - **Negative Testing**: Malformed inputs, invalid types (if language allows), logical contradictions.
   - **Complexity**: Time/Space limits.

# Output Format
Return a single, valid JSON object. Do not include markdown formatting.

JSON Template:
{temp_requirement}

# Input Data
[Problem Description]:
{problem_desc}

[Sample Testcase]:
{input_output_formatted}"""
    return PROMPT_REQUIREMENT_EXTRACTION



def get_prompt_requirement_analysis(problem_desc):

    temp = """{{
  "entry_point": "function_or_class_name",
  "dependencies": ["list", "of", "imports", "needed"],
  "test_strategy_hints": "One of: ['Pure Logic', 'File System I/O', 'Network/Mocking', 'Data Transformation']",
  
  "inputs": [
    {{"name": "arg_name", "type": "str/int/...", "valid_examples": ["val1"], "invalid_examples": ["val2"]}}
  ],
  
  "happy_path_scenarios": [
    "Description of a standard success case",
    "Description of a boundary success case (e.g., empty list if allowed)"
  ],
  
  "negative_scenarios": [
    {{"condition": "Description of error condition", "expected_exception": "ValueError", "expected_message_part": "substring of error message"}}
  ],
  
  "side_effects": [
    "Creates a file at ...",
    "Modifies input dictionary in-place",
    "Calls subprocess..."
  ],
  
  "hardcoded_constraints": [
    "Path must start with /api or /login",
    "Default timeout is 0.5"
  ]
}}"""

    prompt = f"""# Role
You are a **Senior Technical Business Analyst** and **QA Architect**. Your goal is to dissect a software problem description into structured, testable requirements. You are NOT writing code yet; you are defining **WHAT** needs to be tested.

# Input Data
[Problem Description / Docstring]:
{problem_desc}

# Analysis Objectives (The "QA Mindset")
You must perform a deep analysis to extract the following:

1.  **Entry Point:** Identify the main function/class name.
2.  **Input Domain (Equivalence Classes):**
    * What are valid inputsextra (e.g., "Non-empty string", "Positive integer", "Existing file path")
    * What are invalid inputsextra (e.g., "None", "Empty list", "Negative radius")
3.  **Output & Behavior:**
    * What is the return type and formatextra (e.g., "List of strings", "Base64 encoded string")
    * **Side Effects:** Does it write to a fileextra Print to stdoutextra Call an APIextra (Crucial for mocking)
4.  **Exception Contract (CRITICAL):**
    * List EVERY exception mentioned in the `Raises` section or implied by the logic.
    * Extract the **EXACT** error message templates if provided (e.g., "Failed to connect to {{server}}").
5.  **Constants & Literals:**
    * Extract specific strings/numbers that act as "Business Rules" (e.g., default timeout = 30, specific path prefixes like '/api').

# Output Format
Return **ONLY** a valid JSON object matching the schema below. Do not add markdown blocks or comments.
{temp}
"""
    return prompt
    
def requirement_extraction(problem_desc: str, input_output: str = None, api: str = "api_1") -> str:
    """Auto-translated documentation for requirement_extraction."""

    prompt = get_prompt_requirement_extraction1(
            problem_desc=problem_desc,
            input_output=input_output
        )
    print(f"Requirement extraction prompt:\n{prompt}")

    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)
    print(f"Requirement extraction output:\n{llm_output}")

    fixed_code = extract_json_from_llm_response(llm_output)

    return fixed_code, prompt_tokens, completion_tokens


def requirement_analysis(problem_desc: str, api: str = "api_1") -> str:
    """Auto-translated documentation for requirement_analysis."""

    prompt = get_prompt_requirement_analysis(
        problem_desc=problem_desc
    )

    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)

    fixed_code = extract_json_from_llm_response(llm_output)

    return fixed_code, prompt_tokens, completion_tokens


import json
import re

def _escape_newlines_in_json_strings(json_str: str) -> str:
    """
    Escapes literal newlines inside JSON string values.
    LLMs sometimes generate multi-line strings within JSON values,
    which breaks JSON parsing. This function replaces such newlines with \\n.
    """
    result = []
    in_string = False
    escape_next = False
    
    for char in json_str:
        if escape_next:
            result.append(char)
            escape_next = False
            continue
        
        if char == '\\':
            result.append(char)
            escape_next = True
            continue
        
        if char == '"':
            in_string = not in_string
            result.append(char)
            continue
        
        # If we're inside a string and encounter a literal newline, escape it
        if in_string and char == '\n':
            result.append('\\n')
            continue
        
        # Also handle carriage return
        if in_string and char == '\r':
            result.append('\\r')
            continue
        
        result.append(char)
    
    return ''.join(result)


def extract_json_from_llm_response(response_text: str):
    """
    Extracts and parses a JSON object from an LLM's response string.
    It handles:
    1. Pure JSON strings.
    2. Markdown code blocks (```json ... ```).
    3. JSON embedded within other text.
    4. Literal newlines inside string values (LLM artifact).
    """
    
    # 1. Attempt to parse the raw text directly (Best Case)
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass  # Continue to extraction strategies

    # 2. Strategy: Remove Markdown Code Blocks
    # This regex looks for ```json [content] ``` or just ``` [content] ```
    markdown_pattern = r"```(or:json)or\s*([\s\S]*or)\s*```"
    match = re.search(markdown_pattern, response_text, re.IGNORECASE)
    
    candidate_str = ""
    if match:
        candidate_str = match.group(1)
    else:
        # 3. Strategy: Regex to find the outermost JSON object
        # It looks for the first '{' and the last '}' across multiple lines
        # Pattern explanation:
        # \{        : Literal opening brace
        # [\s\S]*   : Match any character (including newlines) greedily
        # \}        : Literal closing brace
        json_pattern = r"\{[\s\S]*\}"
        match_json = re.search(json_pattern, response_text)
        if match_json:
            candidate_str = match_json.group(0)
    
    # 4. Attempt to parse the cleaned/extracted string
    if candidate_str:
        try:
            return json.loads(candidate_str)
        except json.JSONDecodeError:
            pass  # Continue to newline escaping strategy
        
        # 5. Strategy: Escape literal newlines inside JSON string values
        # LLMs sometimes output multi-line text within JSON strings
        try:
            escaped_str = _escape_newlines_in_json_strings(candidate_str)
            return json.loads(escaped_str)
        except json.JSONDecodeError as e:
            print(f"Error parsing extracted JSON (after escaping newlines): {e}")

    return None
