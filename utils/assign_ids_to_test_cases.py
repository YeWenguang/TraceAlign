from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class TestCase:
    input_data: Any
    output_data: Any = None
    description: str = ""
    case_type: str = ""
    test_case_id: int = field(default=None)

def assign_ids_to_test_cases(test_cases: List[TestCase]) -> List[TestCase]:
    """Auto-translated documentation for assign_ids_to_test_cases."""
    for index, tc in enumerate(test_cases, start=1):
        tc.test_case_id = index
    
    return test_cases