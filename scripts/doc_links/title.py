"""Strip an optional markdown link title from a destination."""


def strip_title(inner: str) -> str:
    """Drop an optional markdown link title from a destination.

    Returns:
        The destination without a trailing title.
    """
    text = inner.strip()
    if not text:
        return ""
    if text.startswith("<"):
        end = text.find(">")
        return text[1:end].strip() if end != -1 else text
    for quote in (' "', " '", " ("):
        idx = text.find(quote)
        if idx > 0:
            return text[:idx].strip()
    return text.split()[0]
