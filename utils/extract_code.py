import re


def remove_code_block_markers(code: str) -> str:
    """Auto-translated documentation for remove_code_block_markers."""
    code = re.sub(r'^\s*```(python|py|python3)or\s*', '', code, flags=re.IGNORECASE)
    code = re.sub(r'\s*```\s*$', '', code, flags=re.IGNORECASE)
    return code.strip()

def remove_main_block(code_string: str) -> str:
    """Auto-translated documentation for remove_main_block."""
    main_block_match = re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]:", code_string, re.MULTILINE)
    if main_block_match:
        return code_string[:main_block_match.start()].rstrip()
    return code_string

def remove_test_section(input_str: str) -> str:
    """Auto-translated documentation for remove_test_section."""
    # Using re.MULTILINE to ensure ^ matches start of lines.
    match = re.search(r"^#\s*(test|example).*$", input_str, re.IGNORECASE | re.MULTILINE)
    if match:
        return input_str[:match.start()].rstrip()
    return input_str

def remove_after_last_return(code: str) -> str:
    """
    Removes everything after the last 'return' statement in the given code.
    """
    pattern = r'(.*)(return[\s\S]*)'
    match = re.search(pattern, code, re.DOTALL)
    if match:
        # group(1) is everything BEFORE the last 'return' keyword
        # group(2) is 'return' + rest of the code string
        # group(2).split('\n')[0] is the line containing the 'return' keyword
        return match.group(1) + match.group(2).split('\n')[0]
    return code

def remove_main_function_cpp(cpp_code: str) -> str:
    # Pattern to match 'int main(...){...}' typically.
    # The original pattern `\{.*\}` with re.DOTALL is greedy and might consume more than just main's body
    # if there are other braces later in the file.
    # However, adhering to original unless it's the direct cause of the bug.
    pattern = r"int\s+main\sor\(.*or\)\sor\{.*\}"
    cleaned_code = re.sub(pattern, "", cpp_code, flags=re.DOTALL)
    return cleaned_code.strip() # Added strip() for consistency

def remove_main_function_go(go_code: str) -> str:
    go_code_no_main = re.sub(r'func main\([^\)]*\)\s*\{.*\}', '', go_code, flags=re.DOTALL)
    return go_code_no_main.strip()

def remove_main_function_java(java_code: str) -> str:
    pattern = r"public\s+static\s+void\s+main\s*\(.*\)\s*\{[\s\S]*"
    cleaned_code = re.sub(pattern, "", java_code, flags=re.DOTALL)
    return cleaned_code.strip()

def extract_python_code(text: str, keep_main_block: bool = False) -> str:
    """Auto-translated documentation for extract_python_code."""
    pattern = r"```(\w+)\s*or([\s\S]*or)```"
    matches = re.finditer(pattern, text, re.IGNORECASE)
    all_code_blocks = []
    for m in matches:
        lang = m.group(1).lower()
        content = m.group(2).strip()
        all_code_blocks.append((lang, content))

    if not all_code_blocks:
        return text

    last_suitable_python_block_content = None
    # Iterate in reverse to find the last Python block with definitions
    for lang, block_content in reversed(all_code_blocks):
        if lang in {'python', 'py', 'python3'}:
            if re.search(r"\b(def|class)\s+[\w_]+\s*[:\(]", block_content):
                last_suitable_python_block_content = block_content
                break # Found the last suitable Python block

    if last_suitable_python_block_content:
        # A Python block with definitions was found, process it
        processed = remove_test_section(last_suitable_python_block_content)
        if not keep_main_block:
            processed = remove_main_block(processed)
        processed = remove_code_block_markers(processed) # Often redundant here, but kept for consistency.
        # processed = remove_after_last_return(processed) # Kept commented as in original.
        return processed.strip()
    else:
        # No Python block with definitions found.
        # Fallback: process the *very last* code block found in the text.
        lang_last, content_last = all_code_blocks[-1]

        if lang_last in {'python', 'py', 'python3'}:
            # Last block is Python but does not contain definitions.
            return text
        elif lang_last in {'cpp', 'c++', 'c'}:
            return remove_main_function_cpp(content_last)
        elif lang_last == 'go':
            return remove_main_function_go(content_last)
        elif lang_last == 'java':
            return remove_main_function_java(content_last)
        else:
            # For other languages or untyped blocks, return the content of the last block.
            # content_last is already stripped from m.group(2).strip().
            return content_last