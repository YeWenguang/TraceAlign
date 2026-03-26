import ast
import re

def remove_test_case_from_source(full_source: str, test_case_code: str) -> str:
    """Auto-translated documentation for remove_test_case_from_source."""
    func_name = ""
    match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)", test_case_code)
    if match:
        func_name = match.group(1)
    elif re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", test_case_code.strip()):
        func_name = test_case_code.strip()
    else:
        print(f"Warning: Invalid test case identifier: {test_case_code}")
        return full_source

    print(f"Attempting to remove test case: '{func_name}' via AST...")

    try:
        tree = ast.parse(full_source)
    except SyntaxError:
        print("Error: Source code has syntax errors, cannot parse.")
        return full_source

    target_node = None
    parent_map = {}

    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[child] = node
            
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            target_node = node
            break
    
    if not target_node:
        print(f"Warning: Function '{func_name}' not found in AST.")
        return full_source

    start_line = target_node.lineno
    end_line = target_node.end_lineno
    
    if target_node.decorator_list:
        start_line = target_node.decorator_list[0].lineno

    lines = full_source.splitlines(keepends=True)
    
    
    parent = parent_map.get(target_node)
    should_add_pass = False
    indentation = ""
    
    if isinstance(parent, ast.ClassDef):
        other_stmts = [n for n in parent.body if n != target_node]
        if not other_stmts:
            should_add_pass = True
            original_line = lines[target_node.lineno - 1]
            indentation = original_line[:len(original_line) - len(original_line.lstrip())]

    # lines[0] is line 1.
    # remove lines[start-1] to lines[end-1]
    
    del lines[start_line - 1 : end_line]
    
    if should_add_pass:
        print("Notice: Inserting 'pass' to maintain valid class syntax.")
        lines.insert(start_line - 1, f"{indentation}pass\n")

    new_source = "".join(lines)
    print(f"Success: Removed '{func_name}' (Lines {start_line}-{end_line})")
    
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        print(f"CRITICAL: Removal resulted in invalid syntax! Reverting. ({e})")
        return full_source

    return new_source