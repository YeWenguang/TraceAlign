import re

def trim_long_docstrings(code_content: str, max_lines: int = 4) -> str:
    """Auto-translated documentation for trim_long_docstrings."""
    lines = code_content.splitlines()
    new_lines = []
    
    lines_iterator = iter(lines)

    for line in lines_iterator:
        new_lines.append(line)
        
        stripped_line = line.strip()
        if stripped_line.startswith('def '):
            
            try:
                docstring_first_line = next(lines_iterator)
                stripped_doc_line = docstring_first_line.strip()
                
                quote_type = None
                if stripped_doc_line.startswith('"""'):
                    quote_type = '"""'
                elif stripped_doc_line.startswith("'''"):
                    quote_type = "'''"

                if quote_type:
                    docstring_lines = [docstring_first_line]
                    is_single_line_docstring = (
                        stripped_doc_line.endswith(quote_type) and len(stripped_doc_line) > len(quote_type)
                    )

                    if not is_single_line_docstring:
                        while True:
                            next_doc_line = next(lines_iterator)
                            docstring_lines.append(next_doc_line)
                            if next_doc_line.strip().endswith(quote_type):
                                break
                    
                    full_docstring_text = "\n".join(docstring_lines)
                    content = full_docstring_text.strip()[len(quote_type):-len(quote_type)].strip()
                    content_line_count = len(content.splitlines())
                    
                    if content_line_count > max_lines:
                        indentation = docstring_first_line[:len(docstring_first_line) - len(docstring_first_line.lstrip())]
                        
                        trimmed_content_lines = content.splitlines()[:max_lines]
                        
                        new_docstring = [f"{indentation}{quote_type}"]
                        new_docstring.extend([f"{indentation}{content_line}" for content_line in trimmed_content_lines])
                        new_docstring.append(f"{indentation}{quote_type}")
                        
                        new_lines.extend(new_docstring)
                    else:
                        new_lines.extend(docstring_lines)
                else:
                    new_lines.append(docstring_first_line)

            except StopIteration:
                break
                
    return "\n".join(new_lines)
