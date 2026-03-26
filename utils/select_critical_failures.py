# from dataclasses import dataclass
# from typing import List
# from utils.TracePy import ResultStatus
# import json

# @dataclass
# class FailureSelectionReport:

# def select_critical_failures(results, limit: int = 1) -> FailureSelectionReport:
#     """
    
#     Args:
        
#     Returns:
#     """
#     crashes = [r for r in results if r.status == ResultStatus.CRASH]
#     mismatches = [r for r in results if r.status == ResultStatus.MISMATCH]
    
#     total_crash = len(crashes)
#     total_mismatch = len(mismatches)
    
#     selected = []
    
#     if crashes:
#         crashes.sort(key=lambda x: len(x.trace_log))
#         selected = crashes[:limit]
        
#     elif mismatches:
#         mismatches.sort(key=lambda x: len(str(x.input_str))) 
#         selected = mismatches[:limit]
    
#     return FailureSelectionReport(
#         selected_failures=selected,
#         total_crash_count=total_crash,
#         total_mismatch_count=total_mismatch,
#         extracted_count=len(selected)
#     )



from dataclasses import dataclass
from typing import List
from utils.TracePy import ResultStatus, ExecutionResult 

@dataclass
class FailureSelectionReport:
    """Auto-translated documentation for FailureSelectionReport."""
    selected_failures: List['ExecutionResult']
    total_error_count: int
    total_fail_count: int
    total_timeout_count: int
    extracted_count: int

def select_critical_failures(results: List['ExecutionResult'], limit: int = 1) -> FailureSelectionReport:
    """Auto-translated documentation for select_critical_failures."""
    timeouts = [r for r in results if r.status == ResultStatus.TIMEOUT]
    errors = [r for r in results if r.status == ResultStatus.ERROR]
    failures = [r for r in results if r.status == ResultStatus.FAIL]
    
    total_timeout = len(timeouts)
    total_error = len(errors)
    total_fail = len(failures)
    
    selected = []
    
    
    # (1) Timeouts
    if len(selected) < limit and timeouts:
        needed = limit - len(selected)
        selected.extend(timeouts[:needed])
        
    # (2) Errors
    if len(selected) < limit and errors:
        needed = limit - len(selected)
        errors.sort(key=lambda x: len(x.trace_log) if x.trace_log else float('inf'))
        selected.extend(errors[:needed])
        
    # (3) Failures
    if len(selected) < limit and failures:
        needed = limit - len(selected)
        failures.sort(key=lambda x: len(x.test_case) if x.test_case else float('inf'))
        selected.extend(failures[:needed])
    
    return FailureSelectionReport(
        selected_failures=selected,
        total_error_count=total_error,
        total_fail_count=total_fail,
        total_timeout_count=total_timeout,
        extracted_count=len(selected)
    )

