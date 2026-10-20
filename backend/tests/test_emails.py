import json
from pathlib import Path

import pytest

from backend.identity.emails import is_email, tidy_email

# The same cases as the staff app's rule (frontend/src/ui/email.test.ts), so the
# two never disagree about what an address is.
CASES = json.loads(
    (Path(__file__).parents[2] / "frontend/src/ui/email.cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("email", CASES["valid"])
def test_accepts(email):
    assert is_email(email)


@pytest.mark.parametrize("email", CASES["invalid"])
def test_refuses(email):
    assert not is_email(email)


def test_tidies_as_the_staff_app_does():
    # The same as frontend/src/ui/email.test.ts, so a pasted address sent before
    # the field tidied it (Enter straight away) reads the same here.
    assert tidy_email("  Ana@Gmail.COM ") == "ana@gmail.com"
    assert tidy_email("<ana@gmail.com>") == "ana@gmail.com"
    assert tidy_email(" MAILTO:Ana@gmail.com") == "ana@gmail.com"
