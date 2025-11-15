"""
Template Parser Utilities

Helper functions for placeholder extraction and template analysis.
"""

import re
from typing import List


def extract_placeholders(template: str) -> List[str]:
    """
    Extract all {{placeholder}} patterns from template.

    Args:
        template: Email template string

    Returns:
        List of unique placeholders (including braces)

    Example:
        >>> extract_placeholders("Hi {{name}}, I loved {{research}}!")
        ['{{name}}', '{{research}}']
    """
    # Match {{variable}} pattern
    pattern = r'\{\{[^}]+\}\}'
    matches = re.findall(pattern, template)

    # Return unique placeholders in order of appearance
    seen = set()
    unique_matches = []
    for match in matches:
        if match not in seen:
            seen.add(match)
            unique_matches.append(match)

    return unique_matches