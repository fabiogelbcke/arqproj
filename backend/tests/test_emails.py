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


def test_tidies():
    assert tidy_email("  Ana@Gmail.COM ") == "ana@gmail.com"
