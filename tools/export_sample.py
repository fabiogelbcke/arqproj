"""Write the demo project tree to disk so it can be uploaded to Google Drive.

    python -m tools.export_sample            # → ./sample-drive/Projects/...

Drag the resulting "Projects" folder into Drive (folder structure is kept),
then share it with the service account.
Google-native items in the demo (the _project doc, the Slides deck) are written
as _project.txt and a PDF — the app reads both.
"""

import os
import sys

from tools.fake_drive import DOC, FOLDER, SHORTCUT, SLIDES, FakeDrive, _tiny_pdf

# Keep uploads small: the demo's fake CAD/model files are just zero-filled.
MAX_FAKE_BYTES = 1_500_000


def write(node, fake: FakeDrive, dest: str) -> int:
    count = 0
    if node.mime == SHORTCUT:
        return 0  # can't be recreated by uploading files
    if node.mime == FOLDER:
        path = os.path.join(dest, node.name)
        os.makedirs(path, exist_ok=True)
        for child in node.children:
            count += write(child, fake, path)
        return count
    if node.mime == DOC:
        name, data = f"{node.name}.txt", (node.text or "").encode("utf-8")
    elif node.mime == SLIDES:
        name, data = f"{node.name}.pdf", _tiny_pdf(node.name)
    else:
        name, data = node.name, node.content
        if data.strip(b"\0").startswith(b"AC") or not data.strip(b"\0"):
            data = data[:MAX_FAKE_BYTES]
    with open(os.path.join(dest, name), "wb") as fh:
        fh.write(data)
    os.utime(os.path.join(dest, name), (node.modified.timestamp(), node.modified.timestamp()))
    return 1


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sample-drive"
    fake = FakeDrive("http://unused")
    n = write(fake.nodes[fake.root_id], fake, out)
    print(f"wrote {n} files to {os.path.join(out, 'Projects')}")
