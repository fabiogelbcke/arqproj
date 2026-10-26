from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.transfers import measured

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("fail", [False, True])
async def test_measures_served_bytes_and_outcome_without_content(fail):
    client = Mock()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(posthog=client)),
        state=SimpleNamespace(tenant=SimpleNamespace(slug="alinea")),
    )
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
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(posthog=client)),
        state=SimpleNamespace(tenant=SimpleNamespace(slug="alinea")),
    )
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
