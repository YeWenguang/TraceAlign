import ast
from typing import Tuple, Optional

def check_compilation_error(code_str: str) -> Tuple[bool, Optional[str]]:
    """Auto-translated documentation for check_compilation_error."""
    try:
        compile(code_str, filename="<string>", mode="exec")
        return True, None
        
    except SyntaxError as e:
        error_msg = f"SyntaxError: {e.msg} (Line {e.lineno})"
        if e.text:
             error_msg += f"\nCode: {e.text.strip()}"
        return False, error_msg
        
    except ValueError as e:
        return False, f"ValueError: {str(e)}"
        
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)}"


if __name__ == "__main__":
    code_good = """
def hello():
    print("Hello World")
    return True
"""
    valid, msg = check_compilation_error(code_good)
    print(f"Good Code: {valid}, Error: {msg}")

    code_bad_syntax = """
def hello():
    print("Hello World"
    return True
"""
    valid, msg = check_compilation_error(code_bad_syntax)
    print(f"Bad Syntax: {valid}, Error: {msg}")

    code_bad_indent = """
def hello():
print("Wrong Indent")
"""
    valid, msg = check_compilation_error(code_bad_indent)
    print(f"Bad Indent: {valid}, Error: {msg}")