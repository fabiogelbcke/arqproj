import tempfile
import unittest
from pathlib import Path

from arq.drive import DriveFile
from arq.projects import FileEntry
from tools.fake_drive import FakeDrive, _tiny_pdf
from tools.folder_drive import FolderDrive


class ThumbnailExamples(unittest.TestCase):
    def test_image_without_drive_thumbnail_uses_its_actual_bytes(self):
        image = DriveFile('example-photo', 'Foto.jpg', 'image/jpeg', size=1000)
        self.assertIs(FileEntry(image).thumb, image)
        image.size = 9 * 1024 * 1024
        self.assertIsNone(FileEntry(image).thumb)

    def test_local_pdf_thumbnail_is_rendered_from_the_file(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, 'Documento.pdf').write_bytes(_tiny_pdf('Documento'))
            drive = FolderDrive('http://unused', temp)
            node = next(n for n in drive.nodes.values() if n.name == 'Documento.pdf')
            self.assertTrue(node.thumb)
            self.assertTrue(drive.actual_thumbnails[node.id].startswith(b'\x89PNG'))

    def test_generated_examples_are_portuguese_by_default(self):
        drive = FakeDrive('http://unused')
        names = {n.name for n in drive.nodes.values()}
        self.assertIn('Fotos do local', names)
        self.assertIn('Plantas – rev B.pdf', names)
        self.assertNotIn('Site photos', names)
        config = next(n for n in drive.nodes.values() if n.name == '_project' and 'Slug: casa-jardim' in (n.text or ''))
        self.assertIn('Título:', config.text)
        self.assertNotIn('A single-family house', config.text)
