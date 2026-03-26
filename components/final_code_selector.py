"""Artifact release module."""

import logging
from typing import List, Dict, Tuple, Optional
from llm.client import call_openai_api
from utils.extract_code import extract_python_code

logger = logging.getLogger(__name__)


def get_final_selection_prompt(problem_desc: str, code_candidates: List[Dict[str, any]]) -> str:
    """Auto-translated documentation for get_final_selection_prompt."""
    candidates_section = []
    for i, candidate in enumerate(code_candidates, 1):
        code = candidate.get('code', '')
        pass_count = candidate.get('pass_count', 0)
        total_count = candidate.get('total_count', 0)
        
        candidates_section.append(f"""
- Generated-test pass rate: {pass_count}/{total_count} (reference only; generated tests may still be imperfect)

```python
{code}
```
""")
    
    candidates_text = "\n".join(candidates_section)
    
    prompt = f"""# Role
You are a Senior Python Code Reviewer tasked with selecting the best code implementation from multiple candidates.

# Problem Description
{problem_desc}

# Candidate Code Implementations
{candidates_text}

# IMPORTANT NOTES
- **ALL candidates have passed the sample test cases** (the examples in the problem description), so they are all likely correct
- The "generated test pass rate" is for reference only - generated tests may contain errors and should NOT be the primary decision factor
- Your task is to select the implementation that BEST matches the problem description and is MOST general/flexible

# Selection Criteria (Priority Order)

## 1. Correctness against Problem Description (MOST IMPORTANT)
- The code MUST correctly implement the requirements specified in the Problem Description
- Carefully compare each candidate against the problem description's requirements
- The code MUST handle all edge cases mentioned or implied in the problem
- **Trust the sample test cases in the problem description** - they are the ground truth

## 2. Generality & Flexibility (VERY IMPORTANT - KEY CRITERIA)
- **PREFER the most general and flexible implementation**
- **AVOID over-specific implementations that only work for narrow cases**
- The code should handle a wide range of valid inputs gracefully
- **Look for solutions that make fewer assumptions about input format**
- **Prefer solutions that work for broader problem classes**, not just the specific examples
- If one candidate has stricter input validation or narrower scope, prefer the more permissive one (as long as it's still correct)

## 3. Robustness
- The code should handle edge cases appropriately
- Prefer defensive programming where it makes sense
- Avoid fragile assumptions about input format

## 4. Simplicity & Clarity
- Prefer clean, readable, and maintainable code
- Avoid unnecessary complexity or convoluted logic
- Well-documented code is preferred

## 5. Performance
- Reasonable time and space complexity
- Avoid obviously inefficient algorithms when a better alternative exists

# Instructions
1. **Carefully read the Problem Description** - understand what the function is supposed to do
2. **Analyze each candidate** against the Problem Description (not just the generated test results)
3. Compare the candidates based on the Selection Criteria above
4. **IMPORTANT**: When comparing two correct implementations, choose the one that is MORE GENERAL and LESS RESTRICTIVE
5. Select the ONE best implementation that best balances correctness and generality
6. Provide your reasoning for the selection

# Output Format

## Analysis
Provide a brief analysis of each candidate:
- Candidate #1: [strengths and weaknesses, especially note how well it matches the problem description and how general it is]
- Candidate #2: [strengths and weaknesses, especially note how well it matches the problem description and how general it is]
... (for all candidates)

## Selection
Selected Candidate: #[number]

## Reasoning
Explain why this candidate was selected based on the criteria above. Focus on:
1. **Why it correctly implements the problem description** (most important)
2. **Why it's the most general/robust (explain why it's less restrictive than others)**
3. Any trade-offs considered

## Selected Code
```python
# Paste the complete selected code here, exactly as provided
```
"""
    return prompt


def select_best_code(
    problem_desc: str,
    code_candidates: List[Dict[str, any]],
    api: str = "api_1"
) -> Tuple[str, str, int, int]:
    """Auto-translated documentation for select_best_code."""
    if not code_candidates:
        logger.warning("No code candidates provided for selection")
        return "", "No candidates available", 0, 0
    
    if len(code_candidates) == 1:
        logger.info("Only one candidate available, returning it directly")
        candidate = code_candidates[0]
        return candidate.get('code', ''), "Only one candidate available", 0, 0
    
    prompt = get_final_selection_prompt(problem_desc, code_candidates)
    
    response_text, prompt_tokens, completion_tokens = call_openai_api(prompt)
    
    selected_code = extract_python_code(response_text)
    
    if not selected_code:
        logger.warning("Failed to extract code from LLM response, attempting to match with candidates")
        for i, candidate in enumerate(code_candidates, 1):
            candidate_code = candidate.get('code', '')
            if candidate_code and len(candidate_code) > 50:
                lines = candidate_code.strip().split('\n')
                for line in lines:
                    if line.strip().startswith('def '):
                        if line.strip() in response_text:
                            logger.info(f"Matched candidate #{i} by function definition")
                            return candidate_code, response_text, prompt_tokens, completion_tokens
                        break
        
        best_candidate = max(code_candidates, key=lambda x: x.get('pass_count', 0))
        logger.info(f"Falling back to candidate with highest pass rate: {best_candidate.get('pass_count', 0)}")
        return best_candidate.get('code', ''), response_text, prompt_tokens, completion_tokens
    
    return selected_code, response_text, prompt_tokens, completion_tokens


def collect_passing_candidates(
    dataset: Dict,
    code_history: List[Dict[str, any]],
    test_cases: str,
    run_test_cases_func,
    check_correctness_func,
    max_candidates: int = 5
) -> List[Dict[str, any]]:
    """Auto-translated documentation for collect_passing_candidates."""
    candidates = []
    seen_codes = set()
    
    for entry in code_history:
        code = entry.get('code', '')
        if not code:
            continue
        
        code_hash = hash(code.strip())
        if code_hash in seen_codes:
            continue
        seen_codes.add(code_hash)
        
        sample_result = check_correctness_func(dataset, code, timeout=10)
        if not sample_result.get('passed', False):
            continue
        
        if test_cases:
            results, pass_count, total_count = run_test_cases_func(code, test_cases)
        else:
            pass_count, total_count = 0, 0
        
        candidate = {
            'code': code,
            'pass_count': pass_count,
            'total_count': total_count,
            'loop_number': entry.get('loop_number', 0),
            'metadata': entry.get('metadata', {})
        }
        candidates.append(candidate)
    
    candidates.sort(key=lambda x: (x.get('pass_count', 0), x.get('loop_number', 0)), reverse=True)
    
    return candidates[:max_candidates]
