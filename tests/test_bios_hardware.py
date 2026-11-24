"""Tests for BiosHardware execution, dependency checks, and safety backup invariants."""

import tempfile
from pathlib import Path
import unittest

from scewin_gui.config import AppConfig
from scewin_gui.core import (
    BackupVault,
    BiosExecutionError,
    BiosHardware,
    BiosOperationResult,
    BiosPermissionError,
    BiosTimeoutError,
    DriverGuard,
    NvramValidationError,
    SafetyBackupError,
)

SAMPLE_NVRAM = """// Valid NVRAM for import/export testing
Setup Question = Secure Boot
Help String = Enable or disable secure boot
Token = 2000
Offset = 20
BIOS Default = [00]Disabled
Options = *[00]Disabled
          [01]Enabled
"""


class TestBiosHardware(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmp.name)
        self.config = AppConfig(
            backup_directory="backups",
            nvram_file="nvram.txt",
            nvram_new_file="nvram_new.txt",
            scewin_executable="SCEWIN_64.exe",
        )
        self.vault = BackupVault(self.base_dir / "backups")

        # Create dummy binaries
        (self.base_dir / "SCEWIN_64.exe").write_bytes(b"dummy_exe_content_with_enough_length_for_reading_test_data")
        (self.base_dir / "amifldrv64.sys").write_bytes(b"dummy_drv1_content_with_enough_length_for_reading_test_data")
        (self.base_dir / "amigendrv64.sys").write_bytes(b"dummy_drv2_content_with_enough_length_for_reading_test_data")

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_creates_auto_backup(self):
        commands_run = []

        def fake_runner(cmd: list[str], timeout: int) -> BiosOperationResult:
            commands_run.append(cmd)
            # Simulate SCEWIN outputting nvram.txt
            (self.base_dir / "nvram.txt").write_text(SAMPLE_NVRAM, encoding="utf-8")
            return BiosOperationResult(success=True, description="export", action="export", stdout="Export OK")

        hw = BiosHardware(config=self.config, vault=self.vault, runner=fake_runner, base_dir=self.base_dir)
        hw.check_dependencies = lambda: unittest.mock.MagicMock(ok=True)

        res = hw.execute_export()
        self.assertTrue(res.success)
        self.assertEqual(len(commands_run), 1)
        self.assertIn("/o", commands_run[0])
        self.assertTrue(Path(res.backup_path).is_file())

    def test_driver_guard_lifecycle(self):
        called = False
        with DriverGuard.guard(driver_names=("dummy_drv",)):
            called = True
        self.assertTrue(called)

    def test_export_failure_raises(self):
        def fake_runner(cmd: list[str], timeout: int) -> BiosOperationResult:
            return BiosOperationResult(success=False, description="export", action="export", return_code=1, stderr="Hardware error")

        hw = BiosHardware(config=self.config, vault=self.vault, runner=fake_runner, base_dir=self.base_dir)
        hw.check_dependencies = lambda: unittest.mock.MagicMock(ok=True)

        with self.assertRaises(BiosExecutionError):
            hw.execute_export()

    def test_import_requires_pre_existing_export_and_creates_safety_backup(self):
        # Without existing nvram.txt, import must fail before calling process
        hw = BiosHardware(config=self.config, vault=self.vault, runner=lambda cmd, t: BiosOperationResult(True, "", ""), base_dir=self.base_dir)
        hw.check_dependencies = lambda: unittest.mock.MagicMock(ok=True)

        new_file = self.base_dir / "new.txt"
        new_file.write_text(SAMPLE_NVRAM, encoding="utf-8")

        with self.assertRaises(SafetyBackupError):
            hw.execute_import(str(new_file))

        # Now create nvram.txt and verify safety backup is created
        (self.base_dir / "nvram.txt").write_text(SAMPLE_NVRAM, encoding="utf-8")
        commands_run = []

        def fake_runner(cmd: list[str], timeout: int) -> BiosOperationResult:
            commands_run.append(cmd)
            return BiosOperationResult(success=True, description="import", action="import", stdout="Import OK")

        hw.runner = fake_runner
        res = hw.execute_import(str(new_file))
        self.assertTrue(res.success)
        self.assertEqual(len(commands_run), 1)
        self.assertIn("/i", commands_run[0])
        self.assertTrue(Path(res.backup_path).is_file())

    def test_driver_guard_lifecycle(self):
        called = False
        with DriverGuard.guard(driver_names=("dummy_drv",)):
            called = True
        self.assertTrue(called)


if __name__ == "__main__":
    import unittest.mock
    unittest.main()
