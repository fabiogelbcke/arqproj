"""File stores: one contract for every store, plus the Google client's handling
of Google's answers (without calling Google)."""

from pathlib import Path

import httpx2
import pytest

from backend.settings import Settings
from backend.storage.base import StorageError, StorageItem, StorageProblem
from backend.storage.connections import storage_for
from backend.storage.folder import FolderStorage
from backend.storage.google import GoogleDriveStorage
from backend.storage.memory import MemoryStorage
from backend.storage.models import StorageConnection, StorageKind

pytestmark = pytest.mark.anyio

PDF = b"%PDF-1.4 planta"


# -- the contract every store keeps -----------------------------------------------


def memory_store(_tmp_path):
    store = MemoryStorage()
    store.add_folder("root", "Projetos")
    store.add_folder("casa", "Casa Jardim", parent="root")
    store.add_folder("briefing", "01 - Briefing", parent="casa")
    store.add_file("planta", "Planta v2.pdf", "briefing", PDF, "application/pdf")
    store.add_file("foto", "área externa.jpg", "briefing", b"jpg", "image/jpeg")
    return store, {"casa": "casa", "briefing": "briefing", "planta": "planta"}


def folder_store(tmp_path: Path):
    briefing = tmp_path / "Casa Jardim" / "01 - Briefing"
    briefing.mkdir(parents=True)
    (briefing / "Planta v2.pdf").write_bytes(PDF)
    (briefing / "área externa.jpg").write_bytes(b"jpg")
    (tmp_path.parent / "outside.txt").write_text("not the office's")
    return FolderStorage(tmp_path), {
        "casa": "Casa Jardim",
        "briefing": "Casa Jardim/01 - Briefing",
        "planta": "Casa Jardim/01 - Briefing/Planta v2.pdf",
    }


@pytest.fixture(params=[memory_store, folder_store], ids=["memory", "folder"])
def store(request, tmp_path):
    return request.param(tmp_path)


async def test_a_folder_lists_its_children_by_name(store):
    storage, ids = store
    children = await storage.list_folder(ids["briefing"])
    assert [c.name for c in children] == ["área externa.jpg", "Planta v2.pdf"]
    assert (await storage.list_folder(ids["casa"]))[0].is_folder


async def test_a_file_has_its_details_and_bytes(store):
    storage, ids = store
    item = await storage.get(ids["planta"])
    assert (item.name, item.mime_type, item.size, item.is_folder) == (
        "Planta v2.pdf",
        "application/pdf",
        len(PDF),
        False,
    )
    download = await storage.download(item)
    assert b"".join([chunk async for chunk in download.chunks]) == PDF
    assert download.media_type == "application/pdf"


@pytest.mark.parametrize(("first", "last"), [(2, 5), (0, 0), (5, len(PDF) - 1)])
async def test_a_byte_range_is_just_those_bytes(store, first, last):
    storage, ids = store
    download = await storage.download(await storage.get(ids["planta"]), (first, last))
    assert b"".join([chunk async for chunk in download.chunks]) == PDF[first : last + 1]
    assert download.size == last - first + 1


@pytest.mark.parametrize("item_id", ["nope", "../outside.txt"])
async def test_unknown_items_and_paths_outside_are_not_found(store, item_id):
    storage, _ = store
    with pytest.raises(StorageError) as error:
        await storage.get(item_id)
    assert error.value.problem is StorageProblem.NOT_FOUND


async def test_a_file_is_not_a_folder(store):
    storage, ids = store
    with pytest.raises(StorageError):
        await storage.list_folder(ids["planta"])


# -- which store an office gets -------------------------------------------------------


def test_a_local_folder_is_never_used_when_deployed(tmp_path):
    connection = StorageConnection(kind=StorageKind.FOLDER, root_id="")
    google = object()
    local = Settings(environment="local", local_storage_root=str(tmp_path))
    assert isinstance(storage_for(connection, local, google), FolderStorage)
    deployed = local.model_copy(update={"environment": "staging"})
    with pytest.raises(RuntimeError, match="local development only"):
        storage_for(connection, deployed, google)


# -- the Google client, against an imitation of the Drive API -------------------------


class FakeDrive:
    """Answers the few Drive endpoints we call; records the requests."""

    def __init__(self):
        self.requests: list[httpx2.Request] = []
        self.answers: list[tuple[int, object]] = []  # queued for the next requests

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        status, body = self.answers.pop(0)
        if isinstance(body, bytes):
            return httpx2.Response(status, content=body)
        return httpx2.Response(status, json=body)


def drive_file(file_id, name, mime="application/pdf", size="10"):
    data = {"id": file_id, "name": name, "mimeType": mime, "modifiedTime": "2026-10-15T12:00:00Z"}
    if size is not None:
        data["size"] = size
    return data


FOLDER1 = {
    "id": "folder1",
    "name": "01 - Briefing",
    "mimeType": "application/vnd.google-apps.folder",
    "modifiedTime": "2026-10-15T12:00:00Z",
}


def drive_error(status, reason, message="secret detail from Google"):
    return status, {"error": {"code": status, "message": message, "errors": [{"reason": reason}]}}


@pytest.fixture
def drive():
    fake = FakeDrive()
    waits = []

    async def token():
        return "test-token"

    async def no_wait(seconds):
        waits.append(seconds)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(fake))
    storage = GoogleDriveStorage(token, client, api="https://drive.test/v3", sleep=no_wait)
    fake.waits = waits
    return storage, fake


async def test_a_long_folder_is_read_page_by_page(drive):
    storage, fake = drive
    fake.answers = [
        (200, FOLDER1),
        (200, {"files": [drive_file("b", "B.pdf")], "nextPageToken": "p2"}),
        (200, {"files": [drive_file("a", "A.pdf")]}),
    ]
    assert [i.name for i in await storage.list_folder("folder1")] == ["A.pdf", "B.pdf"]
    _, first, second = fake.requests
    assert first.url.params["q"] == "'folder1' in parents and trashed = false"
    assert "pageToken" not in first.url.params and second.url.params["pageToken"] == "p2"
    assert first.headers["Authorization"] == "Bearer test-token"


async def test_an_id_that_could_change_the_search_is_refused_without_asking_google(drive):
    storage, fake = drive
    with pytest.raises(StorageError) as error:
        await storage.list_folder("x' or name contains '")
    assert error.value.problem is StorageProblem.NOT_FOUND and fake.requests == []


async def test_a_google_document_downloads_as_pdf(drive):
    storage, fake = drive
    doc = StorageItem("doc1", "Memorial", "application/vnd.google-apps.document", None, None)
    fake.answers = [(200, b"%PDF exported")]
    download = await storage.download(doc)
    assert b"".join([c async for c in download.chunks]) == b"%PDF exported"
    assert download.media_type == "application/pdf"
    assert fake.requests[0].url.path.endswith("/files/doc1/export")


async def test_throttling_is_retried_with_growing_waits(drive):
    storage, fake = drive
    fake.answers = [
        drive_error(403, "userRateLimitExceeded"),
        (500, {}),
        (200, drive_file("a", "A.pdf")),
    ]
    assert (await storage.get("a")).name == "A.pdf"
    assert len(fake.waits) == 2 and fake.waits[0] < fake.waits[1]


@pytest.mark.parametrize(
    ("answer", "problem", "attempts"),
    [
        ((404, {}), StorageProblem.NOT_FOUND, 1),
        (drive_error(403, "insufficientFilePermissions"), StorageProblem.NO_ACCESS, 1),
        (drive_error(429, "rateLimitExceeded"), StorageProblem.RATE_LIMITED, 4),
        ((503, {}), StorageProblem.UNAVAILABLE, 4),
    ],
)
async def test_failures_become_problems_without_googles_text(drive, answer, problem, attempts):
    storage, fake = drive
    fake.answers = [answer] * 4
    with pytest.raises(StorageError) as error:
        await storage.get("a")
    assert error.value.problem is problem
    assert "secret detail" not in str(error.value)
    if answer[1]:  # Google's words are kept for the server log
        assert "secret detail" in error.value.detail
    assert len(fake.requests) == attempts  # only worth retrying is retried


async def test_a_shortcut_is_recognised_and_not_downloaded(drive):
    """Following one needs a check that the target is inside the office's folder
    (step 2.5); until then a shortcut is never fetched."""
    storage, fake = drive
    shortcut = drive_file("s1", "Planta (atalho)", "application/vnd.google-apps.shortcut", None)
    fake.answers = [
        (200, FOLDER1),
        (200, {"files": [shortcut | {"shortcutDetails": {"targetId": "elsewhere"}}]}),
    ]
    [item] = await storage.list_folder("folder1")
    assert (item.is_shortcut, item.is_native, item.shortcut_target) == (True, False, "elsewhere")
    with pytest.raises(StorageError):
        await storage.download(item)
    assert len(fake.requests) == 2  # no export or download attempted


async def test_a_failed_login_to_google_is_a_storage_problem_too(drive):
    storage, fake = drive

    async def broken_token():
        raise RuntimeError("could not find default credentials")

    storage._token = broken_token
    with pytest.raises(StorageError) as error:
        await storage.get("a")
    assert error.value.problem is StorageProblem.UNAVAILABLE
    assert "default credentials" in error.value.detail  # for the server log only
    assert "default credentials" not in str(error.value) and fake.requests == []


@pytest.mark.parametrize(
    "folder_answer",
    [(200, FOLDER1 | {"trashed": True}), (404, {}), (200, drive_file("folder1", "a file"))],
    ids=["trashed", "deleted", "a-file"],
)
async def test_a_broken_folder_binding_is_not_found_rather_than_empty(drive, folder_answer):
    storage, fake = drive
    fake.answers = [folder_answer]
    with pytest.raises(StorageError) as error:
        await storage.list_folder("folder1")
    assert error.value.problem is StorageProblem.NOT_FOUND
    assert len(fake.requests) == 1  # never searched for children


async def test_a_connection_dropping_mid_download_is_a_storage_problem(drive):
    storage, fake = drive

    class Broken(httpx2.AsyncByteStream):
        async def __aiter__(self):
            yield b"%PDF first part"
            raise httpx2.ReadError("connection reset")

    def answer(request):
        fake.requests.append(request)
        return httpx2.Response(200, stream=Broken())

    storage._client = httpx2.AsyncClient(transport=httpx2.MockTransport(answer))
    item = StorageItem("f1", "Planta.pdf", "application/pdf", 100, None)
    download = await storage.download(item)
    with pytest.raises(StorageError) as error:
        _ = [chunk async for chunk in download.chunks]
    assert error.value.problem is StorageProblem.UNAVAILABLE
    assert "connection reset" in error.value.detail


async def test_a_trashed_file_is_not_found(drive):
    storage, fake = drive
    fake.answers = [(200, drive_file("a", "A.pdf") | {"trashed": True})]
    with pytest.raises(StorageError):
        await storage.get("a")


async def test_thumbnails_come_in_the_size_asked(drive):
    storage, fake = drive
    item = StorageItem("img", "Foto.jpg", "image/jpeg", 3, None)
    fake.answers = [(200, {"thumbnailLink": "https://thumbs.test/abc=s220"}), (200, b"tiny")]
    assert await storage.thumbnail(item, size=640) == b"tiny"
    assert str(fake.requests[1].url) == "https://thumbs.test/abc=s640"
    fake.answers = [(200, {})]
    assert await storage.thumbnail(item) is None


# -- one office's view of a Drive the reader shares with other offices --------------


def office_drive(drive, root="rootA"):
    from backend.storage.google import OfficeDrive

    storage, fake = drive
    return OfficeDrive(storage, root), fake


async def test_an_office_reads_only_inside_its_own_folder(drive):
    office, fake = office_drive(drive)
    # planta → stage1 → rootA: inside; reached by walking up the parents.
    fake.answers = [(200, {"parents": ["stage1"]}), (200, {"parents": ["rootA"]})]
    fake.answers.append((200, drive_file("planta", "Planta.pdf")))
    assert (await office.get("planta")).name == "Planta.pdf"
    # Another office's file: its parents lead elsewhere, and its details are
    # never fetched.
    fake.answers = [(200, {"parents": ["rootB"]}), (200, {"parents": []})]
    asked = len(fake.requests)
    with pytest.raises(StorageError) as error:
        await office.get("their-file")
    assert error.value.problem is StorageProblem.NOT_FOUND
    assert all("fields=parents" in str(r.url) for r in fake.requests[asked:])


async def test_what_is_listed_inside_the_office_needs_no_second_check(drive):
    office, fake = office_drive(drive)
    folder = FOLDER1 | {"id": "rootA"}
    fake.answers = [(200, folder), (200, {"files": [drive_file("f1", "Planta.pdf")]})]
    await office.list_folder("rootA")  # the root itself: no parent walk
    fake.answers = [(200, drive_file("f1", "Planta.pdf"))]
    asked = len(fake.requests)
    await office.get("f1")  # confirmed by the listing
    assert len(fake.requests) == asked + 1


async def test_a_google_format_without_pdf_export_is_not_downloaded(drive):
    storage, fake = drive
    video = StorageItem("v1", "Apresentação", "application/vnd.google-apps.vid", None, None)
    with pytest.raises(StorageError):
        await storage.download(video)
    assert fake.requests == []


def test_an_office_on_google_gets_a_view_limited_to_its_folder():
    from backend.storage.google import OfficeDrive

    connection = StorageConnection(
        kind=StorageKind.GOOGLE, root_id="rootA", reader_identity="r@x.iam"
    )
    assert isinstance(storage_for(connection, Settings(), google=object()), OfficeDrive)


async def test_a_download_abandoned_before_reading_can_still_be_closed(drive):
    storage, fake = drive
    closed = []

    class Body(httpx2.AsyncByteStream):
        async def __aiter__(self):
            yield b"%PDF"

        async def aclose(self):
            closed.append(True)

    def answer(request):
        return httpx2.Response(200, stream=Body())

    storage._client = httpx2.AsyncClient(transport=httpx2.MockTransport(answer))
    download = await storage.download(StorageItem("f1", "P.pdf", "application/pdf", 4, None))
    await download.aclose()  # the client went away before the first chunk
    assert closed


async def test_a_byte_range_is_asked_of_google_as_one(drive):
    storage, fake = drive
    fake.answers = [(200, drive_file("f1", "Planta.pdf"))]
    item = await storage.get("f1")
    fake.answers = [(206, b"2345"), (200, drive_file("f1", "Planta.pdf"))]
    download = await storage.download(item, (2, 5))
    assert b"".join([c async for c in download.chunks]) == b"2345"
    assert (download.size, fake.requests[-2].headers["Range"]) == (4, "bytes=2-5")


async def test_a_range_of_a_file_replaced_since_its_check_is_refused(drive):
    """A reader can't pin a Drive revision: the file is asked for again once its
    part is coming, and a new version's bytes never join a resumed download."""
    storage, fake = drive
    fake.answers = [(200, drive_file("f1", "Planta.pdf"))]
    item = await storage.get("f1")
    replaced = drive_file("f1", "Planta.pdf") | {"modifiedTime": "2026-10-15T12:00:05Z"}
    fake.answers = [(206, b"2345"), (200, replaced)]
    with pytest.raises(StorageError) as raised:
        await storage.download(item, (2, 5))
    assert raised.value.problem == StorageProblem.UNAVAILABLE


async def test_a_range_google_answers_with_the_whole_file_is_refused(drive):
    """Sent as the part, the whole file would corrupt a resumed download."""
    storage, fake = drive
    item = StorageItem("f1", "Planta.pdf", "application/pdf", 10, None)
    fake.answers = [(200, b"0123456789")]
    with pytest.raises(StorageError) as raised:
        await storage.download(item, (2, 5))
    assert raised.value.problem == StorageProblem.UNAVAILABLE


async def test_a_google_documents_export_ignores_a_range(drive):
    storage, fake = drive
    doc = StorageItem("doc1", "Memorial", "application/vnd.google-apps.document", None, None)
    fake.answers = [(200, b"%PDF exported")]
    download = await storage.download(doc, (2, 5))
    assert b"".join([c async for c in download.chunks]) == b"%PDF exported"
    assert "Range" not in fake.requests[0].headers and download.size is None
