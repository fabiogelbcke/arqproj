"""The scheduler's call to the maintenance pass (A09, A19): only Google's signed
token for the scheduler's account runs it; everything else is a 404."""

import pytest

from backend.tests import test_office
from backend.web import maintenance

owner = test_office.owner  # fixtures

pytestmark = pytest.mark.anyio

AUDIENCE = "https://portal-staging.example.run.app"
CALLER = "portal-scheduler@arq-proj.iam.gserviceaccount.com"
RUN_APP = {"host": "portal-staging.example.run.app"}  # no office's address


@pytest.fixture
def configured(app, tmp_path, monkeypatch):
    app.state.settings = app.state.settings.model_copy(
        update={
            "maintenance_audience": AUDIENCE,
            "maintenance_caller": CALLER,
            "email_outbox": str(tmp_path / "outbox"),
        }
    )
    app.state.http = None  # the local outbox needs no HTTP client
    seen = []

    def verify(token, audience):
        seen.append(audience)
        if token != "good":
            raise ValueError("Token used too late")
        return {"email": CALLER, "email_verified": True}

    monkeypatch.setattr(maintenance, "_verify", verify)
    return seen


def call(client, token="good", host=RUN_APP):
    headers = host | ({"authorization": f"Bearer {token}"} if token else {})
    return client.post("/internal/maintenance", headers=headers)


async def test_the_scheduler_runs_a_pass_on_the_services_own_address(client, owner, configured):
    response = await call(client)
    assert response.status_code == 200, response.text
    assert set(response.json()) >= {"offices", "projects", "new_files", "emails", "failed"}
    assert configured == [AUDIENCE]  # checked against this service, not any


@pytest.mark.parametrize("token", [None, "forged"])
async def test_without_googles_token_there_is_nothing_here(client, owner, configured, token):
    assert (await call(client, token=token)).status_code == 404


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "someone@gmail.com", "email_verified": True},  # another Google account
        {"email": CALLER, "email_verified": False},
    ],
)
async def test_only_the_schedulers_account_may_call(client, owner, configured, monkeypatch, claims):
    monkeypatch.setattr(maintenance, "_verify", lambda token, audience: claims)
    assert (await call(client)).status_code == 404


async def test_unconfigured_the_address_does_not_exist(client, owner):
    assert (await call(client)).status_code == 404


async def test_a_refused_token_never_reaches_the_logs(
    client, owner, configured, monkeypatch, caplog
):
    """google-auth's messages can quote the token: only the kind of error is logged."""

    def leaks(token, audience):
        raise ValueError(f"Wrong number of segments in token: {token}")

    monkeypatch.setattr(maintenance, "_verify", leaks)
    secret = "ya29.a0-access-token-not-a-jwt"
    assert (await call(client, token=secret)).status_code == 404
    assert caplog.records and all(secret not in r.getMessage() for r in caplog.records)
