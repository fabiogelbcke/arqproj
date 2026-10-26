"""A zip written while it downloads (A37, "Baixar tudo"; plan section 15).

Stored, not compressed: architects' files (PDF, images, CAD) barely shrink, and
an uncompressed zip's length follows from its files' sizes, so the browser shows
real progress. Each file's CRC is only known once its bytes have passed, so it
follows the file in a data descriptor (flag bit 3); names are UTF-8 (bit 11) so
"Ampliação" reads right on Windows and macOS. No zip64: a link holds at most
300 MB.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

FLAGS = 0x0808  # data descriptor after each file, UTF-8 names
VERSION = 20  # 2.0: what a stored file with a descriptor needs
LOCAL = 30  # a local header's fixed part
DESCRIPTOR = 16
CENTRAL = 46
END = 22


@dataclass(frozen=True)
class Entry:
    name: str  # its path inside the zip: "01 Briefing/Planta.pdf"
    size: int | None  # None: not known before it downloads (a Google format)
    modified_at: datetime  # in the office's time: a zip's times have no zone


def length(entries: list[Entry]) -> int | None:
    """The zip's exact size in bytes, or None when a file's size isn't known."""
    if any(entry.size is None for entry in entries):
        return None
    names = sum(len(entry.name.encode()) for entry in entries)
    data = sum(entry.size or 0 for entry in entries)
    return len(entries) * (LOCAL + DESCRIPTOR + CENTRAL) + 2 * names + data + END


def part(text: str) -> str:
    """One folder or file name inside the zip: Drive allows "/" ("Planta 1/50.pdf"),
    which would make folders, and ".." would point outside the zip's own folder."""
    cleaned = text.replace("/", "-").replace("\\", "-").strip()
    return cleaned if cleaned not in ("", ".", "..") else "_"


def unique_names(names: list[str]) -> list[str]:
    """The same path twice (two stages' "Planta.pdf" land in their own folders;
    a subfolder's file can still meet one): "Planta (2).pdf" for the second."""
    seen: set[str] = set()
    out = []
    for name in names:
        folder, slash, base = name.rpartition("/")
        candidate, n = name, 2
        while candidate.casefold() in seen:
            stem, dot, extension = base.rpartition(".")
            numbered = f"{stem} ({n}).{extension}" if dot and stem else f"{base} ({n})"
            candidate = f"{folder}{slash}{numbered}"
            n += 1
        seen.add(candidate.casefold())
        out.append(candidate)
    return out


def _dos(moment: datetime) -> tuple[int, int]:
    year = max(moment.year, 1980)
    time = (moment.hour << 11) | (moment.minute << 5) | (moment.second // 2)
    date = ((year - 1980) << 9) | (moment.month << 5) | moment.day
    return time, date


class SizeChanged(Exception):
    """A file sent other bytes than its listing said: the promised length is wrong."""


async def stream(
    entries: list[Entry], open_file: Callable[[int], Awaitable[AsyncIterator[bytes]]]
) -> AsyncIterator[bytes]:
    """The zip's bytes. `open_file(i)` gives entry i's chunks, opened only when its
    turn comes (so one upstream download is open at a time)."""
    offset = 0
    central = []
    for index, entry in enumerate(entries):
        name = entry.name.encode()
        time, date = _dos(entry.modified_at)
        header = struct.pack(
            "<IHHHHHIIIHH", 0x04034B50, VERSION, FLAGS, 0, time, date, 0, 0, 0, len(name), 0
        )
        yield header + name
        crc, size = 0, 0
        async for chunk in await open_file(index):
            crc = zlib.crc32(chunk, crc)
            size += len(chunk)
            yield chunk
        if entry.size is not None and size != entry.size:
            raise SizeChanged(entry.name)
        yield struct.pack("<IIII", 0x08074B50, crc, size, size)
        central.append(
            struct.pack(
                "<IHHHHHHIIIHHHHHII",
                0x02014B50,
                VERSION,
                VERSION,
                FLAGS,
                0,
                time,
                date,
                crc,
                size,
                size,
                len(name),
                0,
                0,
                0,
                0,
                0,
                offset,
            )
            + name
        )
        offset += LOCAL + len(name) + size + DESCRIPTOR
    directory = b"".join(central)
    yield directory
    yield struct.pack(
        "<IHHHHIIH", 0x06054B50, 0, 0, len(entries), len(entries), len(directory), offset, 0
    )
