import re
import secrets

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str, *, max_len: int = 80) -> str:
    """Lowercase, hyphen-separated, alphanumeric-only slug."""
    base = _SLUG_RE.sub("-", title.lower()).strip("-")
    if not base:
        base = "post"
    if len(base) > max_len:
        base = base[:max_len].rstrip("-")
    return base


def with_suffix(base: str) -> str:
    """Append a short random hex to break a uniqueness collision."""
    return f"{base}-{secrets.token_hex(2)}"
