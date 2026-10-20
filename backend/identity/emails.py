"""Email addresses as people type them, checked the same way everywhere (the staff
app checks with the same rule while it's typed: frontend/src/ui/email.ts)."""

import re

EMAIL_MAX = 254  # the longest address mail servers accept

_LOCAL = re.compile(r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?")


def tidy_email(raw: str) -> str:
    """Trimmed and lowercase, without what comes along when one is pasted from an
    email program ("<ana@x.com>", "mailto:ana@x.com"): as the staff app's tidyEmail."""
    email = raw.strip()
    email = re.sub(r"^mailto:", "", email, flags=re.IGNORECASE)
    email = re.sub(r"^<(.*)>$", r"\1", email)
    return email.strip().lower()


def is_email(email: str) -> bool:
    """A name, "@", and a domain of at least two parts ending in letters
    ("ana@escritorio.com.br"), with no spaces or doubled dots. Expects it tidied."""
    if len(email) > EMAIL_MAX:
        return False
    local, at, domain = email.rpartition("@")
    if not at or not 0 < len(local) <= 64:
        return False
    labels = domain.split(".")
    return (
        _LOCAL.fullmatch(local) is not None
        and len(labels) >= 2
        and all(len(label) <= 63 and _LABEL.fullmatch(label) for label in labels)
        and re.fullmatch(r"[a-z]{2,}", labels[-1]) is not None
    )
