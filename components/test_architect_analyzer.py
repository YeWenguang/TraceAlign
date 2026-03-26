from typing import List, Dict, Any, Optional
from llm.client import call_openai_api, call_openai_api2
import json
import re
from dataclasses import dataclass
from utils.extract_code import extract_python_code
import logging
logger = logging.getLogger(__name__)

def get_prompt_test_architect(problem_desc):

    DEPENDENCY_SCHEMA = """{
  "class_name": "Name of the class",
  "has_init": boolean,
  "methods": [
    {
      "name": "method_name",
      "signature": "method_name(self, arg1, ...)",
      "type": "Entry Point" or "Helper",
      "description": "Brief summary of what this method does",
      "internal_calls": ["list", "of", "other_methods_in_this_class_called_by_this_method"],
      "external_dependencies": ["logging", "datetime", "subprocess", "etc"],
      "reads_attributes": ["self.attribute_name"],
      "modifies_attributes": ["self.attribute_name"]
    }
  ],
  "integration_scenarios": [
    {
      "test_case_name": "test_entry_point_logic",
      "target_method": "name_of_entry_point_method",
      "mocking_plan": [
        {"target": "helper_method_name", "behavior": "return_value or side_effect description"},
        {"target": "external_lib", "behavior": "mock behavior"}
      ]
    }
  ]
}"""

    PROMPT_CLASS_ANALYSIS = f"""# Role
You are a **Senior Python Static Analyst** and **Test Architect**. Your task is to dissect the provided Python Class to build a "Method Call Graph" and "Dependency Map". This analysis will be used to generate strictly isolated unit tests.

# Input Data
[Class Description/Code]:
{problem_desc}

# Analysis Objectives
You must analyze the code to answer three key questions:
1.  **Hierarchy:** Which methods are the "Public Interface" (Entry Points) and which are "Internal Logic" (Helpers)or
2.  **Flow:** When an Entry Point is called, which Internal Helpers does it invokeextra (e.g., `process()` calls `_validate()` and `_save()`).
3.  **State & Side Effects:** Does the method rely on `self.variable`extra Does it call external I/O (Network, File, DB)or

# Critical Analysis Rules
1.  **Identify Calls:** If method A calls `self.method_B()`, you MUST record `method_B` in A's `internal_calls` list.
2.  **Identify External Libs:** Look for *any* import usage (e.g., `os`, `requests`, `time`). These MUST be identified for mocking.
3.  **Mocking Strategy:**
    * We want to test **Entry Points**.
    * To do this safely, we usually **Mock the Helpers** to control the internal flow.
    * *Example:* If testing `filter()`, and `filter()` calls `get_jwt_user()`, we should Mock `get_jwt_user` to return a fixed dictionary, rather than creating a real JWT token.

# Output Format
Return **ONLY** a valid JSON object matching the schema below.
**Do not** include markdown code blocks (```json), comments, or conversational text.
**Do not** output the schema itself, just the filled data.

[JSON Schema]:
{DEPENDENCY_SCHEMA}
"""
    return PROMPT_CLASS_ANALYSIS
    
def test_architect_analysis(problem_desc: str, api: str = "api_1") -> str:
    """Auto-translated documentation for test_architect_analysis."""

    prompt = get_prompt_test_architect(
        problem_desc=problem_desc
    )
    print(f"Test architecture analysis prompt:\n{prompt}")

    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)
    print(f"Test architecture analysis output:\n{llm_output}")

    fixed_code = extract_json_from_llm_response(llm_output)

    return fixed_code


import json
import re

def extract_json_from_llm_response(response_text: str):
    """
    Extracts and parses a JSON object from an LLM's response string.
    It handles:
    1. Pure JSON strings.
    2. Markdown code blocks (```json ... ```).
    3. JSON embedded within other text.
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
    try:
        if candidate_str:
            return json.loads(candidate_str)
    except json.JSONDecodeError as e:
        print(f"Error parsing extracted JSON: {e}")
        # Optional: Print candidate_str to debug what went wrong
        # print(f"Candidate String: {candidate_str}")

    return None
