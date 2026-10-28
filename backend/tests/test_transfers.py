from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.transfers import measured

pytestmark = pytest.mark.anyio

PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1"


def fake_request(client, user_agent=PHONE):
    settings = SimpleNamespace(app_secret="s" * 32, deployed=False)
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(posthog=client, settings=settings)),
        state=SimpleNamespace(tenant=SimpleNamespace(slug="alinea")),
        headers={"user-agent": user_agent},
        client=SimpleNamespace(host="203.0.113.5"),
    )


@pytest.mark.parametrize("fail", [False, True])
async def test_measures_served_bytes_and_outcome_without_content(fail):
    client = Mock()
    request = fake_request(client)
    project = SimpleNamespace(tenant_id="tenant-1")
    closed = []

    async def chunks():
        try:
            yield b"ab"
            yield b"cde"
            if fail:
                raise OSError("private detail")
        finally:
            closed.append(True)

    async def read():
        return [c async for c in measured(request, project, chunks(), "share_download")]

    if fail:
        with pytest.raises(OSError):
            await read()
    else:
        assert await read() == [b"ab", b"cde"]
    assert closed == [True]
    props = client.capture.call_args.kwargs["properties"]
    assert props["bytes"] == 5 and props["complete"] is not fail
    assert props["$process_person_profile"] is False
    assert props["$groups"] == {"tenant": "tenant-1"}
    assert "private" not in repr(props) and "ab" not in repr(props)


async def test_cancelled_transfer_closes_upstream_and_reports_partial():
    client = Mock()
    request = fake_request(client)
    closed = []

    async def chunks():
        try:
            yield b"abc"
            yield b"def"
        finally:
            closed.append(True)

    stream = measured(request, SimpleNamespace(tenant_id="t"), chunks(), "preview")
    assert await anext(stream) == b"abc"
    await stream.aclose()
    assert closed == [True]
    assert client.capture.call_args.kwargs["properties"]["bytes"] == 3
    assert client.capture.call_args.kwargs["properties"]["complete"] is False


@pytest.mark.parametrize("staff", [False, True])
async def test_says_whether_staff_or_a_visitor_downloaded_and_on_what(staff):
    """A visitor's download counts under the day's anonymous id, so distinct
    downloaders can be counted; staff's under the office, as before."""
    client = Mock()

    async def chunks():
        yield b"abc"

    request = fake_request(client)
    [_ async for _ in measured(request, SimpleNamespace(tenant_id="t"), chunks(), "x", staff=staff)]
    sent = client.capture.call_args.kwargs
    assert sent["properties"]["viewer"] == ("staff" if staff else "visitor")
    assert sent["properties"]["device"] == "phone"
    assert sent["distinct_id"].startswith("tenant:" if staff else "visitor:")
    assert "203.0.113.5" not in repr(sent)  # the address only ever goes into the hash
