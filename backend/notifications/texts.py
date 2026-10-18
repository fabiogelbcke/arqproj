"""The email's and the unsubscribe page's words, from the site's translation files
(backend/i18n), so they change where every other text does."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from backend.tenancy.models import Locale

_FOLDER = Path(__file__).resolve().parent.parent / "i18n"


@cache
def _texts(locale: Locale) -> dict:
    return json.loads((_FOLDER / f"{locale.value}.json").read_text("utf-8"))["email"]


def t(locale: Locale, key: str, count: int | None = None, **values) -> str:
    """As the site's `t`: `{{name}}` filled in; `_one`/`_other` by `count`."""
    texts = _texts(locale)
    if count is not None:
        key = f"{key}_{'one' if count == 1 else 'other'}"
        values["count"] = count
    text = texts[key]
    for name, value in values.items():
        text = text.replace("{{" + name + "}}", str(value))
    return text
