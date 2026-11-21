"""Offline integration checks: no real vendor process can run in this suite."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from scewin_gui.core import BiosParser, DependencyStatus, SafetyBackupError
from scewin_gui.desktop_api import DesktopApi

SAMPLE = """// Synthetic fixture, not a BIOS dump
Setup Question = Memory Frequency
Help String = Numeric parameter
Token = 1000
Offset = 10
BIOS Default = <0>
Value = <1> // keep this comment

Setup Question = Boot Mode
Help String = Duplicate labels with distinct option IDs
Token = 1001
Offset = 11
BIOS Default = [00]Auto
Options = [00]Auto
         *[01]Enabled
          [02]Enabled
"""


class FakeWindow:
    def __init__(self):
        self.paths = None
        self.confirm = True
        self.confirmations = []

    def create_file_dialog(self, *_args, **_kwargs):
        return self.paths

    def create_confirmation_dialog(self, title, message):
        self.confirmations.append((title, message))
        return self.confirm


class DesktopApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scewin_api_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "nvram.txt").write_text(SAMPLE, encoding="utf-8")
        self.api = DesktopApi(base_dir=self.root)
        patch("scewin_gui.desktop_api.logger.exception").start()
        self.window = FakeWindow()
        self.api._window = self.window
        # Any accidental real subprocess invocation fails this test.
        self.runner = patch("scewin_gui.desktop_api.subprocess.run",
                            side_effect=AssertionError("Real vendor execution forbidden")).start()
        self.addCleanup(patch.stopall)
        self.state = self.call("bootstrap")

    def call(self, action, **payload):
        result = self.api.request(action, payload)
        self.assertTrue(result["ok"], result)
        return result["data"]

    def edit(self, index=0, value="AB"):
        return self.call("edit", document_id=self.api._document_id, id=index, value=value)

    def enable_vendor_stub(self, *, returncode=0):
        self.api._service.check_dependencies = Mock(return_value=DependencyStatus(True, [], [], [], False))
        self.runner.side_effect = None
        self.runner.return_value = subprocess.CompletedProcess([], returncode, "done", "failure" if returncode else "")

    def test_bootstrap_loads_without_vendor_or_qt(self):
        self.assertEqual(len(self.state["settings"]), 2)
        self.assertFalse(self.state["dirty"])
        self.assertFalse(self.state["dependencies"]["ok"])
        self.runner.assert_not_called()

    def test_numeric_and_duplicate_option_ids_round_trip(self):
        self.assertEqual(self.edit()["setting"]["value"], "<AB>")
        self.edit(1, "02")
        self.call("save_changes")
        saved = (self.root / "nvram_new.txt").read_text(encoding="utf-8")
        doc = BiosParser().parse_file(saved)
        self.assertEqual(doc.settings[0].current_value, "<AB>")
        self.assertEqual(doc.settings[1].current_option_id, "02")
        self.assertIn("// keep this comment", saved)
        self.assertEqual((self.root / "nvram.txt").read_text(encoding="utf-8"), SAMPLE)

    def test_partial_save_contains_only_modified_blocks(self):
        self.edit(1, "02")
        data = self.call("save_changes")
        self.assertFalse(data["dirty"])
        doc = BiosParser().parse_file((self.root / "nvram_new.txt").read_text(encoding="utf-8"))
        self.assertEqual([s.name for s in doc.settings], ["Boot Mode"])
        self.assertTrue(self.edit()["dirty"])

    def test_invalid_numbers_and_ids_leave_document_unchanged(self):
        for value in ("GG", "1\nSetup Question = injected", ""):
            result = self.api.request("edit", {"document_id": self.api._document_id, "id": 0, "value": value})
            self.assertFalse(result["ok"])
        result = self.api.request("edit", {"document_id": self.api._document_id, "id": 1, "value": "FF"})
        self.assertFalse(result["ok"])
        self.assertFalse(self.api._dirty())

    def test_stale_document_and_negative_index_rejected(self):
        for identity, index in (("stale", 0), (self.api._document_id, -1), (self.api._document_id, True)):
            result = self.api.request("edit", {"document_id": identity, "id": index, "value": "AB"})
            self.assertFalse(result["ok"])

    def test_revert_and_default(self):
        self.edit()
        data = self.call("reset", document_id=self.api._document_id, id=0, mode="default")
        self.assertEqual(data["setting"]["value"], "<0>")
        data = self.call("reset", document_id=self.api._document_id, id=0, mode="initial")
        self.assertFalse(data["dirty"])
        self.assertFalse(data["setting"]["modified"])

    def test_save_as_full_document_becomes_current_file(self):
        self.edit()
        target = self.root / "edited.txt"
        self.window.paths = (str(target),)
        data = self.call("save_as")
        self.assertFalse(data["dirty"])
        self.assertEqual(data["filepath"], str(target))
        self.assertEqual(len(BiosParser().parse_file(target.read_text(encoding="utf-8")).settings), 2)
        self.assertEqual(data["modified_count"], 0)
        self.assertEqual(len(data["settings"]), 2)

    def test_save_as_cannot_replace_live_export(self):
        self.edit()
        self.window.paths = (str(self.root / "nvram.txt"),)
        self.assertFalse(self.api.request("save_as")["ok"])
        self.assertEqual((self.root / "nvram.txt").read_text(encoding="utf-8"), SAMPLE)

    def test_open_and_close_respect_unsaved_confirmation(self):
        self.edit()
        self.window.confirm = False
        self.window.paths = (str(self.root / "nvram.txt"),)
        old_id = self.api._document_id
        self.assertTrue(self.call("open_file")["cancelled"])
        self.assertEqual(self.api._document_id, old_id)
        self.assertFalse(self.api._on_closing())
        self.window.confirm = True
        self.assertTrue(self.api._on_closing())
        self.assertNotEqual(self.call("open_file")["document_id"], old_id)

    def test_bad_open_preserves_current_document(self):
        target = self.root / "bad.txt"
        target.write_text("invalid file", encoding="utf-8")
        self.window.paths = (str(target),)
        old_id = self.api._document_id
        self.assertFalse(self.api.request("open_file")["ok"])
        self.assertEqual(self.api._document_id, old_id)

    def test_native_close_protects_uncommitted_input(self):
        self.call("draft", document_id=self.api._document_id, id=0, dirty=True)
        self.window.confirm = False
        self.assertFalse(self.api._on_closing())
        self.assertTrue(self.window.confirmations)
        self.window.confirm = True
        self.assertTrue(self.api._on_closing())
        self.call("draft", document_id=self.api._document_id, id=0, dirty=False)
        self.assertFalse(self.api._dirty())

    def test_busy_requests_and_close_are_rejected(self):
        with self.api._lock:
            self.assertFalse(self.api.request("backups")["ok"])
            self.assertFalse(self.api._on_closing())
        self.assertTrue(self.api.request("backups")["ok"])

    def test_backup_create_delete_and_path_boundary(self):
        data = self.call("create_backup")
        path = data["backups"][0]["path"]
        self.assertTrue(Path(path).is_file())
        outside = str(self.root / "nvram.txt")
        self.assertFalse(self.api.request("delete_backup", {"path": outside})["ok"])
        self.window.confirm = False
        self.assertTrue(self.call("delete_backup", path=path)["cancelled"])
        self.window.confirm = True
        self.assertEqual(self.call("delete_backup", path=path)["backups"], [])

    def test_import_requires_confirm_and_backup_before_process(self):
        self.enable_vendor_stub()
        self.edit()
        self.call("save_changes")
        self.window.confirm = False
        self.assertTrue(self.call("bios", operation="import")["cancelled"])
        self.runner.assert_not_called()
        self.window.confirm = True

        def execute(command, **kwargs):
            self.assertTrue(list((self.root / "backups").glob("*.txt")))
            self.assertIn("/i", command)
            self.assertEqual(kwargs["timeout"], 30)
            return subprocess.CompletedProcess(command, 0, "done", "")

        self.runner.side_effect = execute
        self.call("bios", operation="import")
        self.runner.assert_called_once()

    def test_backup_failure_blocks_import(self):
        self.enable_vendor_stub()
        self.api._service.create_safety_backup = Mock(side_effect=SafetyBackupError("backup failed"))
        result = self.api.request("bios", {"operation": "import_loaded"})
        self.assertFalse(result["ok"])
        self.runner.assert_not_called()

    def test_dependency_failure_blocks_vendor(self):
        self.assertFalse(self.api.request("bios", {"operation": "export"})["ok"])
        self.runner.assert_not_called()

    def test_timeout_and_failed_process_release_lock(self):
        self.enable_vendor_stub(returncode=1)
        self.assertFalse(self.api.request("bios", {"operation": "export"})["ok"])
        self.runner.side_effect = subprocess.TimeoutExpired("stub", 30)
        self.assertFalse(self.api.request("bios", {"operation": "export"})["ok"])
        self.assertTrue(self.api.request("backups")["ok"])

    def test_language_persists_and_unknown_actions_rejected(self):
        self.call("language", language="uk")
        self.assertEqual(DesktopApi(base_dir=self.root)._language, "uk")
        self.assertFalse(self.api.request("language", {"language": "invalid"})["ok"])
        self.assertFalse(self.api.request("__getattribute__")["ok"])
        self.assertFalse(self.api.request("external_link", {"link": "file:///arbitrary"})["ok"])


if __name__ == "__main__":
    unittest.main()
