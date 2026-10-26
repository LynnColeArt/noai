"""Filesystem safety and CLI integration contracts."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from noai.cli import main
from noai.project import transform_project


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "output"
        (self.source / "index.html").write_bytes(b'<!DOCTYPE html>\r\n<p>Hello world</p>\r\n')

    def test_copy_recursive_assets_and_source_immutability(self):
        original = (self.source / "index.html").read_bytes()
        (self.source / "nested").mkdir()
        (self.source / "nested" / "INDEX.HTM").write_text("<h1>Hello</h1>")
        (self.source / "asset.bin").write_bytes(bytes(range(256)))
        (self.source / ".git").mkdir()
        (self.source / ".git" / "secret.html").write_text("Hello")
        report = transform_project(self.source, self.output)
        self.assertEqual((report.html_files, report.changed_files, report.copied_files), (2, 2, 1))
        self.assertEqual((self.source / "index.html").read_bytes(), original)
        self.assertEqual((self.output / "asset.bin").read_bytes(), bytes(range(256)))
        self.assertEqual((self.output / "index.html").read_bytes().count(b"\r\n"), 2)
        self.assertFalse((self.output / ".git").exists())

    def test_output_validation(self):
        for output in [self.source, self.source / "nested", self.root]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                transform_project(self.source, output)

    def test_dry_run_and_custom_exclusion(self):
        (self.source / "private").mkdir()
        (self.source / "private" / "bad.html").write_bytes(b'\xff')
        report = transform_project(self.source, self.output, dry_run=True, exclude=frozenset({"private"}))
        self.assertEqual(report.html_files, 1)
        self.assertFalse(self.output.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["source"])

    def test_invalid_utf8_cleans_staging_directory(self):
        (self.source / "broken.html").write_bytes(b'\xff')
        with self.assertRaises(UnicodeDecodeError):
            transform_project(self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["source"])

    def test_symlinks_are_skipped(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.html").write_text("Secret")
        (self.source / "link").symlink_to(outside, target_is_directory=True)
        (self.source / "file.html").symlink_to(outside / "secret.html")
        report = transform_project(self.source, self.output)
        self.assertEqual(report.skipped_symlinks, 2)
        self.assertFalse((self.output / "link").exists())
        self.assertFalse((self.output / "file.html").exists())

    def test_cli_success_and_error_status(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            status = main([str(self.source), "-o", str(self.output), "--dry-run"])
        self.assertEqual(status, 0)
        self.assertIn("Would evacuate 1/1", stdout.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = main([str(self.root / "missing"), "-o", str(self.output)])
        self.assertEqual(status, 1)
        self.assertIn("Source is not a directory", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
