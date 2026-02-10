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
