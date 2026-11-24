"""Tests for NvramDocument, BiosParser, BiosSetting, and BiosDocumentSession."""

import tempfile
from pathlib import Path
import unittest

from scewin_gui.core import (
    BiosDocumentSession,
    BiosParser,
    BiosSetting,
    NvramDocument,
    NvramValidationError,
)

SAMPLE_NVRAM = """// Sample synthetic NVRAM
Setup Question = Memory Frequency
Help String = Configures memory clock
Token = 1000
Offset = 10
BIOS Default = <0>
Value = <1> // preserve comment

Setup Question = Boot Option
Help String = Boot selection
Token = 1001
Offset = 11
BIOS Default = [00]Auto
Options = [00]Auto
         *[01]Enabled

Setup Question = Read Only Register
Help String = Read only hardware info
Token = 1002
Offset = 12
BIOS Default = -
"""


class TestNvramDocument(unittest.TestCase):
    def setUp(self):
        self.parser = BiosParser()
        self.doc = self.parser.parse_file(SAMPLE_NVRAM)

    def test_parsed_settings_count_and_metadata(self):
        self.assertEqual(len(self.doc.settings), 3)
        mem = self.doc.settings[0]
        self.assertEqual(mem.name, "Memory Frequency")
        self.assertEqual(mem.help_string, "Configures memory clock")
        self.assertEqual(mem.token, "1000")
        self.assertEqual(mem.offset, "10")
        self.assertTrue(mem.is_numeric)
        self.assertEqual(mem.current_value, "<1>")

        boot = self.doc.settings[1]
        self.assertEqual(boot.name, "Boot Option")
        self.assertEqual(boot.current_option_id, "01")
        self.assertEqual(boot.current_value, "Enabled")
        self.assertEqual(len(boot.options), 2)

    def test_setting_edit_numeric(self):
        mem = self.doc.settings[0]
        mem.set_value("<2>")
        self.assertEqual(mem.current_value, "<2>")
        self.assertTrue(mem.is_modified)

    def test_setting_edit_option(self):
        boot = self.doc.settings[1]
        boot.set_option("00")
        self.assertEqual(boot.current_option_id, "00")
        self.assertEqual(boot.current_value, "Auto")
        self.assertTrue(boot.is_modified)

    def test_newline_injection_rejection(self):
        mem = self.doc.settings[0]
        with self.assertRaises(ValueError):
            mem.set_value("1\nSetup Question = Injected")

        boot = self.doc.settings[1]
        with self.assertRaises(ValueError):
            boot.set_option("00\r\n")

    def test_document_session_flow(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test_nvram.txt"
            file_path.write_text(SAMPLE_NVRAM, encoding="utf-8")

            session = BiosDocumentSession.open_file(str(file_path), parser=self.parser)
            self.assertFalse(session.is_dirty)
            self.assertEqual(session.modified_count, 0)

            # Draft numeric
            is_dirty = session.set_draft(0, True)
            self.assertTrue(is_dirty)
            self.assertTrue(session.is_dirty)

            # Commit edit
            setting = session.edit(0, "4")
            self.assertEqual(setting.current_value, "<4>")
            self.assertTrue(session.is_dirty)
            self.assertEqual(session.modified_count, 1)

            # Generate changes
            changes = session.generate_changes()
            self.assertIn("Setup Question = Memory Frequency", changes)
            self.assertIn("<4>", changes)
            self.assertNotIn("Boot Option", changes)

            # Save changes
            new_path = Path(tmp_dir) / "nvram_new.txt"
            session.save_changes(str(new_path), lambda p, c: Path(p).write_text(c, encoding="utf-8"))
            self.assertFalse(session.is_dirty)

    def test_save_as_protected_export_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test_nvram.txt"
            file_path.write_text(SAMPLE_NVRAM, encoding="utf-8")
            session = BiosDocumentSession.open_file(str(file_path), parser=self.parser)

            with self.assertRaises(ValueError) as ctx:
                session.save_as(
                    str(file_path),
                    lambda p, c: Path(p).write_text(c, encoding="utf-8"),
                    protected_paths=(str(file_path),),
                )
            self.assertIn("Нельзя перезаписывать базовый файл", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
