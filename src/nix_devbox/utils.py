"""Utility functions shared across modules."""


def expand_flagged_options(flag: str, items: list[str] | None) -> list[str]:
    """Expand a list of items into flag-value pairs.

    Args:
        flag: The flag to use (e.g., "-p", "-v")
        items: List of values to pair with the flag, or None

    Returns:
        List of [flag, value, flag, value, ...] pairs

    Examples:
        >>> expand_flagged_options("-p", ["8080:80", "8443:443"])
        ['-p', '8080:80', '-p', '8443:443']
        >>> expand_flagged_options("-v", None)
        []
    """
    if not items:
        return []
    # Use list comprehension with nested loops for flat list
    return [pair for item in items for pair in (flag, item)]


def extract_part_by_separator(value: str, separator: str, index: int = 0) -> str:
    """Extract a part from string by separator, with fallback to original value.

    Args:
        value: The string to split
        separator: The separator to split on
        index: Which part to return (0-indexed)

    Returns:
        The part at index if separator exists and index is valid, else original value

    Examples:
        >>> extract_part_by_separator('./host:/container:ro', ':', 1)
        '/container'
        >>> extract_part_by_separator('/tmp:size=100m', ':', 0)
        '/tmp'
        >>> extract_part_by_separator('KEY=value', '=', 0)
        'KEY'
    """
    parts = value.split(separator)
    return parts[index] if len(parts) > index else value
