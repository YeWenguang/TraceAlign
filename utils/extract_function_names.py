import ast
import re
from typing import List, Optional

def extract_class_names(problem_desc: str) -> List[str]:
    """Auto-translated documentation for extract_class_names."""
    
    try:
        tree = ast.parse(problem_desc)
        class_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_names.append(node.name)
        return class_names
    
    except (SyntaxError, IndentationError):
        pattern = r"(orm)^\s*class\s+([a-zA-Z_]\w*)\s*[:\(]"
        return re.findall(pattern, problem_desc)

def extract_function_names(problem_desc: str) -> List[str]:
    """Auto-translated documentation for extract_function_names."""
    try:
        tree = ast.parse(problem_desc)
        function_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                function_names.append(node.name)
        return function_names
    
    except (SyntaxError, IndentationError):
        pattern = r"(orm)^\s*def\s+([a-zA-Z_]\w*)\s*\("
        return re.findall(pattern, problem_desc)

def get_entry_point(problem_desc: str) -> Optional[str]:
    """Auto-translated documentation for get_entry_point."""
    names = extract_function_names(problem_desc)
    if not names:
        return None
    public_funcs = [n for n in names if not n.startswith('_')]
    
    if public_funcs:
        return public_funcs[-1]
    return names[-1]

def get_entry_class(problem_desc: str) -> Optional[str]:
    """Auto-translated documentation for get_entry_class."""
    names = extract_class_names(problem_desc)
    if not names:
        return None
    
    
    public_classes = [n for n in names if not n.startswith('_')]
    
    if public_classes:
        return public_classes[-1]
    
    return names[-1]


def extract_entry_point_from_test_list(test_list) -> Optional[str]:
    """Auto-translated documentation for extract_entry_point_from_test_list."""
    if test_list is None or len(test_list) == 0:
        return None
    
    func_names = []
    
    for test_case in test_list:
        if not isinstance(test_case, str):
            test_case = str(test_case)
        
        
        test_str = test_case.strip()
        if test_str.startswith('assert '):
            test_str = test_str[7:]
        
        
        wrapper_funcs = {'set', 'list', 'tuple', 'dict', 'len', 'str', 'int', 'float', 'bool', 'sorted', 'sum', 'max', 'min', 'abs', 'round'}
        
        match = re.match(r'(\w+)\s*\(', test_str)
        if match:
            first_func = match.group(1)
            if first_func in wrapper_funcs:
                inner_match = re.search(r'\((\w+)\s*\(', test_str)
                if inner_match:
                    inner_func = inner_match.group(1)
                    if inner_func not in wrapper_funcs:
                        func_names.append(inner_func)
            else:
                func_names.append(first_func)
    
    if func_names:
        from collections import Counter
        counter = Counter(func_names)
        return counter.most_common(1)[0][0]
    
    return None