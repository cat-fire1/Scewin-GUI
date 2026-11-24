"""Tests for DesktopApi request dispatching using FakeDialogHost and FakeProcessRunner."""

import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock

from scewin_gui.config import AppConfig
from scewin_gui.core import (
    BackupVault,
    BiosHardware,
    BiosOperationResult,
)
from scewin_gui.desktop_api import DesktopApi, FakeDialogHost

SAMPLE_NVRAM = """// Sample synthetic NVRAM for DesktopApi
Setup Question = CPU Frequency
Help String = Adjust multiplier
Token = 3000
Offset = 30
BIOS Default = <100>
Value = <100>

Setup Question = Hyper Threading
Help String = Enable SMT
Token = 3001
Offset = 31
BIOS Default = [01]Enabled
Options = [00]Disabled
         *[01]Enabled
"""


class TestDesktopApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmp.name)
        self.config = AppConfig(
            backup_directory="backups",
            nvram_file="nvram.txt",
            nvram_new_file="nvram_new.txt",
            settings_file="settings.ini",
        )
        self.vault = BackupVault(self.base_dir / "backups")

        # Prepare default nvram.txt
        (self.base_dir / "nvram.txt").write_text(SAMPLE_NVRAM, encoding="utf-8")

        self.fake_dialogs = FakeDialogHost()
        self.commands = []

        def fake_runner(cmd: list[str], timeout: int) -> BiosOperationResult:
            self.commands.append(cmd)
            return BiosOperationResult(success=True, description=" ".join(cmd), action="mock", stdout="OK")

        self.hardware = BiosHardware(
            config=self.config,
            vault=self.vault,
            runner=fake_runner,
            base_dir=self.base_dir,
        )
        self.hardware.check_dependencies = lambda: MagicMock(
            ok=True, missing=[], unreadable=[], tampered=[], hvci_active=False,
            _asdict=lambda: {"ok": True, "missing": [], "unreadable": [], "tampered": [], "hvci_active": False}
        )

        self.api = DesktopApi(
            config=self.config,
            base_dir=self.base_dir,
            runner=fake_runner,
            dialog_host=self.fake_dialogs,
            hardware=self.hardware,
            vault=self.vault,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_bootstrap_loads_initial_state(self):
        res = self.api.request("bootstrap")
        self.assertTrue(res["ok"])
        data = res["data"]
        self.assertEqual(data["app_name"], self.config.app_name)
        self.assertTrue(len(data["settings"]) >= 2)
        self.assertFalse(data["dirty"])

    def test_open_file_cancelled_or_success(self):
        self.api.request("bootstrap")

        # Cancelled
        self.fake_dialogs.open_result = None
        res = self.api.request("open_file")
        self.assertTrue(res["ok"])
        self.assertTrue(res["data"].get("cancelled"))

        # Open valid file
        test_file = self.base_dir / "other.txt"
        test_file.write_text(SAMPLE_NVRAM, encoding="utf-8")
        self.fake_dialogs.open_result = str(test_file)

        res = self.api.request("open_file")
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["filepath"], str(test_file))

    def test_edit_and_reset(self):
        boot = self.api.request("bootstrap")["data"]
        doc_id = boot["document_id"]

        # Edit numeric setting
        res = self.api.request("edit", {"document_id": doc_id, "id": 0, "value": "120"})
        self.assertTrue(res["ok"])
        self.assertTrue(res["data"]["dirty"])
        self.assertEqual(res["data"]["setting"]["value"], "<120>")

        # Reset setting to default
        res = self.api.request("reset", {"document_id": doc_id, "id": 0, "mode": "default"})
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["setting"]["value"], "<100>")

    def test_save_changes_and_save_as(self):
        boot = self.api.request("bootstrap")["data"]
        doc_id = boot["document_id"]

        # Make modification
        self.api.request("edit", {"document_id": doc_id, "id": 0, "value": "150"})

        # Save changes
        res = self.api.request("save_changes")
        self.assertTrue(res["ok"])
        new_file = self.base_dir / "nvram_new.txt"
        self.assertTrue(new_file.is_file())
        self.assertIn("<150>", new_file.read_text(encoding="utf-8"))

        # Save as
        save_target = self.base_dir / "saved_custom.txt"
        self.fake_dialogs.save_result = str(save_target)
        res = self.api.request("save_as")
        self.assertTrue(res["ok"])
        self.assertTrue(save_target.is_file())

    def test_backup_actions(self):
        self.api.request("bootstrap")

        # Create backup
        res = self.api.request("create_backup")
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["data"]["backups"]), 1)
        backup_path = res["data"]["backups"][0]["path"]

        # Delete backup with confirmation
        self.fake_dialogs.confirm_result = True
        res = self.api.request("delete_backup", {"path": backup_path})
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["data"]["backups"]), 0)

    def test_bios_export_and_import(self):
        self.api.request("bootstrap")

        # Export BIOS
        res = self.api.request("bios", {"operation": "export"})
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["data"]["backups"]), 1)

        # Import BIOS
        (self.base_dir / "nvram_new.txt").write_text(SAMPLE_NVRAM, encoding="utf-8")
        self.fake_dialogs.confirm_result = True
        res = self.api.request("bios", {"operation": "import"})
        self.assertTrue(res["ok"])

    def test_language_switch(self):
        res = self.api.request("language", {"language": "en"})
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["language"], "en")


if __name__ == "__main__":
    unittest.main()
