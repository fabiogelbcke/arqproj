"""The zip "Baixar tudo" writes while it downloads (A37): its promised length and
its contents, as other tools read them."""

import io
import zipfile
from datetime import datetime

import pytest

from backend.shares import zipped

pytestmark = pytest.mark.anyio

MOMENT = datetime(2026, 10, 25, 14, 30)


def entries_of(files: dict[str, bytes]) -> list[zipped.Entry]:
    return [zipped.Entry(name, len(data), MOMENT) for name, data in files.items()]


async def written(files: dict[str, bytes], sizes: dict[str, int] | None = None) -> bytes:
    data = list(files.values())
    entries = [
        zipped.Entry(name, (sizes or {}).get(name, len(content)), MOMENT)
        for name, content in files.items()
    ]

    async def open_file(index: int):
        async def chunks():
            content = data[index]
            for start in range(0, len(content), 1000):  # in pieces, as Drive sends them
                yield content[start : start + 1000]

        return chunks()

    return b"".join([chunk async for chunk in zipped.stream(entries, open_file)])


async def test_the_promised_length_is_the_zips_and_any_tool_reads_it():
    files = {
        "01 Briefing/Planta.pdf": b"%PDF " * 3000,
        "02 Levantamento/Ampliação do terraço.dwg": b"dwg",
        "02 Levantamento/vazio.txt": b"",
    }
    out = await written(files)
    assert len(out) == zipped.length(entries_of(files))
    archive = zipfile.ZipFile(io.BytesIO(out))
    assert archive.testzip() is None  # every CRC right
    assert archive.namelist() == list(files)  # accents kept (UTF-8 names)
    assert all(archive.read(name) == content for name, content in files.items())
    assert archive.getinfo("01 Briefing/Planta.pdf").compress_type == zipfile.ZIP_STORED


def test_no_length_is_promised_when_a_size_is_unknown():
    assert zipped.length([zipped.Entry("Memorial.pdf", None, MOMENT)]) is None


async def test_a_file_that_sends_other_bytes_than_listed_breaks_the_download():
    with pytest.raises(zipped.SizeChanged):
        await written({"Planta.pdf": b"%PDF"}, sizes={"Planta.pdf": 10})


def test_the_same_path_twice_gets_a_number():
    assert zipped.unique_names(["A/Planta.pdf", "A/planta.pdf", "A/Planta.pdf", "A/LEIAME"]) == [
        "A/Planta.pdf",
        "A/planta (2).pdf",
        "A/Planta (3).pdf",
        "A/LEIAME",
    ]


def test_a_repeated_name_is_numbered_in_its_own_folder_even_with_dots_there():
    assert zipped.unique_names(["03 Projeto v2.1/Memorial", "03 Projeto v2.1/Memorial"]) == [
        "03 Projeto v2.1/Memorial",
        "03 Projeto v2.1/Memorial (2)",
    ]


def test_a_name_never_makes_folders_or_leaves_the_zips_folder():
    assert zipped.part("Planta 1/50.pdf") == "Planta 1-50.pdf"
    assert zipped.part("a\\b") == "a-b"
    assert zipped.part("..") == "_"
    assert zipped.part(" ") == "_"
