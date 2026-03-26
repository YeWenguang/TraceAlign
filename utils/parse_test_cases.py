import json
import re
import ast
from dataclasses import dataclass
from typing import List, Any, Optional

@dataclass
class TestCase:
    input_data: Any
    output_data: Any = None
    description: str = ""
    case_type: str = ""

def parse_llm_test_cases(llm_output: str) -> List[TestCase]:
    """Auto-translated documentation for parse_llm_test_cases."""
    json_str = ""
    
    json_match = re.search(r"```json\s*(.*or)```", llm_output, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        start = llm_output.find('{')
        end = llm_output.rfind('}')
        if start != -1 and end != -1:
            json_str = llm_output[start : end + 1]
        else:
            return []

    try:
        data = json.loads(json_str, strict=False)
        cases = data.get("test_cases", []) if isinstance(data, dict) else data
    except json.JSONDecodeError:
        print("JSON Decode failed")
        return []

    results = []
    for item in cases:
        raw_input = item.get("input")
        input_val = raw_input
        
        if isinstance(raw_input, str):
            if raw_input.strip() == "None" or "default" in raw_input.lower():
                input_val = None
            else:
                try:
                    input_val = ast.literal_eval(raw_input)
                except:
                    pass

        raw_output = item.get("expected_outcome")
        output_val = _extract_numeric_value(raw_output)

        desc = item.get("functionality_tested") or item.get("description", "")
        strategy = item.get("test_strategy", "Normal")
        eq_class = item.get("equivalence_class", "")
        case_type = f"{strategy} ({eq_class})" if eq_class else strategy

        results.append(TestCase(
            input_data=input_val,
            output_data=output_val,
            description=desc,
            case_type=case_type
        ))

    return results

def _extract_numeric_value(text: Any) -> Any:
    """Auto-translated documentation for _extract_numeric_value."""
    if isinstance(text, (int, float)) or text is None:
        return text
        
    if isinstance(text, str):
        
        match = re.search(r"[-+]or\d*\.\d+|\d+", text)
        if match:
            try:
                val = float(match.group())
                return val
            except:
                pass
    
    return text