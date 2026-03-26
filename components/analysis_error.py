from llm.client import call_openai_api, call_openai_api2
from utils.parse_test_cases import parse_llm_test_cases
from utils.remove_comments import remove_comments
from utils.trim_long_docstrings import trim_long_docstrings
import logging
import re
import json
logger = logging.getLogger(__name__)


def generate_analysis_prompt(requirement, dataset, test_cases1, code, final_result):
    test_list_str = ""
    if 'test_list' in dataset:
        test_list_str = dataset['test_list']
    elif 'public_test_cases' in dataset:
        test_list_str = dataset.get('public_test_cases', 'N/A')
    else:
        test_list_str = "N/A (LiveCodeBench uses private test cases)"
    
    prompt = f"""
# Role
You are an experienced software test architect and code auditing expert.

# Input Data
<Problem_Requirement>
{requirement}
</Problem_Requirement>

<Dataset_Test_Cases>
{test_list_str}
</Dataset_Test_Cases>

<Generated_Test_Cases>
{test_cases1}
</Generated_Test_Cases>

<Fixed_Code>
{code}
</Fixed_Code>

<Final_Failure_Result>
{final_result}
</Final_Failure_Result>

# Task
Analyze why the repaired code still failed the dataset tests.
Compare the failures in <Final_Failure_Result> with the coverage provided by <Generated_Test_Cases>.

Decision rules:
1. If a failing dataset scenario (for example a boundary case or special input) does not appear at all in <Generated_Test_Cases>, conclude "INSUFFICIENT_COVERAGE".
2. If the failing dataset scenario already appears in <Generated_Test_Cases> but the code still fails, conclude "INEFFECTIVE_REPAIR".

# Output Format
Output only the following JSON object:
{{
    "failure_point": "The specific dataset-test failure message",
    "missing_in_generated_tests": true/false,
    "root_cause": "INSUFFICIENT_COVERAGE or INEFFECTIVE_REPAIR",
    "reasoning": "Detailed reasoning"
}}
"""
    return prompt

def generate_analysis_prompt2(requirement, dataset, test_cases1):
    test_list_str = ""
    if 'test_list' in dataset:
        test_list_str = dataset['test_list']
    elif 'public_test_cases' in dataset:
        test_list_str = dataset.get('public_test_cases', 'N/A')
    else:
        test_list_str = "N/A (LiveCodeBench uses private test cases)"
    
    prompt = f"""
# Role
You are an experienced software test architect and code auditing expert.

# Input Data
<Problem_Requirement>
{requirement}
</Problem_Requirement>

<Dataset_Test_Cases>
{test_list_str}
</Dataset_Test_Cases>

<Generated_Test_Cases>
{test_cases1}
</Generated_Test_Cases>

# Task
Analyze why the repaired code still failed the dataset tests.
Compare the failures in <Final_Failure_Result> with the coverage provided by <Generated_Test_Cases>.

Decision rules:
1. If a failing dataset scenario (for example a boundary case or special input) does not appear at all in <Generated_Test_Cases>, conclude "INSUFFICIENT_COVERAGE".
2. If the failing dataset scenario already appears in <Generated_Test_Cases> but the code still fails, conclude "INEFFECTIVE_REPAIR".

# Output Format
Output only the following JSON object:
{{
    "failure_point": "The specific dataset-test failure message",
    "missing_in_generated_tests": true/false,
    "root_cause": "INSUFFICIENT_COVERAGE or INEFFECTIVE_REPAIR",
    "reasoning": "Detailed reasoning"
}}
"""
    return prompt




    
def analysis_error(requirement, dataset, test_cases1, code, final_result, api: str = "api_2"):
    """Auto-translated documentation for analysis_error."""
    logger.info("Starting initial test generation...")
    
    prompt = generate_analysis_prompt(requirement, dataset, test_cases1, code, final_result)

    print(f"Error analysis prompt:\n{prompt}")
        
    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)

    print(f"Error analysis output:\n{llm_output}")

    root_cause = extract_root_cause(llm_output)
    

    return root_cause

def analysis_error2(requirement, dataset, test_cases1, api: str = "api_2"):
    """Auto-translated documentation for analysis_error2."""
    logger.info("Starting initial test generation...")
    
    prompt = generate_analysis_prompt2(requirement, dataset, test_cases1)

    print(f"Error analysis prompt:\n{prompt}")
        
    if api == "api_1":
        llm_output, prompt_tokens, completion_tokens = call_openai_api(prompt)
    else:
        llm_output, prompt_tokens, completion_tokens = call_openai_api2(prompt)

    print(f"Error analysis output:\n{llm_output}")

    root_cause = extract_root_cause(llm_output)
    

    return root_cause
    

def extract_root_cause(llm_output):
    """Auto-translated documentation for extract_root_cause."""
    
    if isinstance(llm_output, dict):
        return llm_output.get("root_cause", "KEY_NOT_FOUND")

    if isinstance(llm_output, str):
        try:
            match = re.search(r'\{.*\}', llm_output, re.DOTALL)
            
            if match:
                json_str = match.group()
                data = json.loads(json_str)
                return data.get("root_cause", "KEY_NOT_FOUND")
            else:
                return "NO_JSON_FOUND"
                
        except json.JSONDecodeError:
            return "JSON_PARSE_ERROR"
        except Exception as e:
            return f"UNKNOWN_ERROR: {str(e)}"

    return "INVALID_INPUT_TYPE"

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
