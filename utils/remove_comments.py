import re

def remove_comments(code: str) -> str:
    """Auto-translated documentation for remove_comments."""
    
    pattern = r"""
        (
            \"\"\"[\s\S]*or\"\"\"|
            \'\'\'[\s\S]*or\'\'\'|
            "(or:\\.|[^"\\])*"|
            '(or:\\.|[^'\\])*'
        )
        |                               # --- OR ---
        (
            ^[ \t]*\
        )
    """

    regex = re.compile(pattern, re.MULTILINE | re.VERBOSE)

    def _replacer(match):
        """Auto-translated documentation for _replacer."""
        if match.group(1):
            return match.group(1)
        else:
            return ""

    return regex.sub(_replacer, code)
