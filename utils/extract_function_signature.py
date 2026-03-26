"""Artifact release module."""
import re


def extract_function_signature_from_code(code: str, prefer_solve: bool = True) -> tuple:
    """Auto-translated documentation for extract_function_signature_from_code."""
    if not code:
        return "", []
    
    all_signatures = []
    all_func_names = []
    solve_signature = None
    solve_func_name = None
    
    pattern = r'^[ \t]*(def\s+(\w+)\s*\([^)]*\)(or:\s*->\s*[^:]+)or:)'
    
    for match in re.finditer(pattern, code, re.MULTILINE):
        full_signature = match.group(1).strip()
        func_name = match.group(2)
        
        if func_name.startswith('_') or func_name.startswith('test_'):
            continue
        
        all_signatures.append(full_signature)
        all_func_names.append(func_name)
        
        if func_name == 'solve':
            solve_signature = full_signature
            solve_func_name = func_name
    
    if prefer_solve and solve_signature:
        return solve_signature, [solve_func_name]
    
    signature_str = "\n".join(all_signatures) if all_signatures else ""
    return signature_str, all_func_names


def extract_func_name_from_signature(signature: str) -> str:
    """Auto-translated documentation for extract_func_name_from_signature."""
    match = re.search(r'def\s+(\w+)\s*\(', signature)
    return match.group(1) if match else signature


if __name__ == "__main__":
    test_code = """
def anagrams(word: str, list_of_words: list) -> list:
    return [w for w in list_of_words if sorted(w) == sorted(word)]

def _helper(x):
    return x * 2

def second_func(a, b):
    return a + b
"""
    
    sig, names = extract_function_signature_from_code(test_code)
    print("Signatures:")
    print(sig)
    print("\nFunction names:", names)
    
    test_sig = "def anagrams(word: str, list_of_words: list) -> list:"
    print(f"\nExtract from '{test_sig}':")
    print(f"  -> '{extract_func_name_from_signature(test_sig)}'")
