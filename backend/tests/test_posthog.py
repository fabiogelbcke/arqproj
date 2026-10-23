"""Product analytics (PostHog, A37): what reaches PostHog when it's configured, and
that nothing changes when it isn't. A stand-in records the calls PostHog's client
would get; nothing leaves the test."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from backend.commands.seed import seed
from backend.identity.models import Role
from backend.tests.test_office import ALINEA, sign_in_as

pytestmark = pytest.mark.anyio


class FakePosthog:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []
        self.identified: list[str] = []
        self.profiles: list[tuple[str, dict]] = []
        self.errors: list[Exception] = []

    @contextmanager
    def new_context(self, fresh=False):
        yield

    def identify_context(self, distinct_id):
        self.identified.append(distinct_id)

    def set(self, distinct_id, properties):
        self.profiles.append((distinct_id, properties))

    def capture(self, event, properties=None, **_):
        self.events.append((event, properties or {}))

    def capture_exception(self, error):
        self.errors.append(error)


@pytest.fixture
def posthog(app):
    fake = FakePosthog()
    app.state.posthog = fake
    return fake


async def test_signing_in_identifies_the_staff_member_and_counts_the_sign_in(
    client, db_session, posthog
):
    await seed(db_session)
    await sign_in_as(client, db_session, "dona@alinea.example", Role.OWNER)
    assert ("staff_signed_in", {"authentication_method": "password"}) in posthog.events
    # The account's id, and its profile: today the name and email go too (A37).
    [(distinct_id, profile)] = posthog.profiles
    assert distinct_id in posthog.identified
    assert profile == {"email": "dona@alinea.example", "name": "Ana", "role": "owner"}


async def test_an_action_sends_its_event_without_personal_data(client, db_session, posthog):
    await seed(db_session)
    owner = await sign_in_as(client, db_session, "dona@alinea.example", Role.OWNER)
    response = await client.post(
        "/api/team/invites",
        json={"name": "Bia Souza", "email": "bia@alinea.example", "role": "member"},
        headers=owner,
    )
    assert response.status_code == 201, response.text
    assert ("staff_invited", {"role": "member"}) in posthog.events
    # The invited person's name and email never go into an event.
    sent = repr(posthog.events)
    assert "bia@alinea.example" not in sent and "Bia Souza" not in sent


async def test_a_request_with_a_staff_session_is_tied_to_that_person(client, db_session, posthog):
    await seed(db_session)
    owner = await sign_in_as(client, db_session, "dona@alinea.example", Role.OWNER)
    signed_in_as = posthog.identified[-1]
    posthog.identified.clear()
    await client.get("/api/me", headers=owner)
    assert posthog.identified == [signed_in_as]


async def test_without_posthog_configured_nothing_changes(app, client, db_session):
    assert getattr(app.state, "posthog", None) is None  # tests run without the two settings
    await seed(db_session)
    owner = await sign_in_as(client, db_session, "dona@alinea.example", Role.OWNER)
    response = await client.get("/api/me", headers=owner)
    assert response.status_code == 200
    assert (await client.get("/api/tenant", headers=ALINEA)).status_code == 200
