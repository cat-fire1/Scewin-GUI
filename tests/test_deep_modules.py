"""Direct interface unit tests for the deepened domain modules."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scewin_gui.config import AppConfig
from scewin_gui.core import (
    BackupItem,
    BackupVault,
    BiosDocumentSession,
    BiosExecutionError,
    BiosExecutor,
    BiosOperationResult,
    BiosParser,
    BiosPermissionError,
    BiosService,
    BiosTimeoutError,
    DependencyStatus,
    NvramValidationError,
    SafetyBackupError,
)

SAMPLE_NVRAM = """// Synthetic NVRAM test file
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
          [02]Disabled
"""


class FakeProcessRunner:
    def __init__(self, return_code: int = 0, stdout: str = "success", stderr: str = ""):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.invocations: list[tuple[list[str], int]] = []
        self.raise_exc: Exception | None = None

    def __call__(self, command: list[str], timeout: int) -> BiosOperationResult:
        self.invocations.append((command, timeout))
        if self.raise_exc:
            raise self.raise_exc
        return BiosOperationResult(
            success=self.return_code == 0,
            description=" ".join(command),
            action="",
            stdout=self.stdout,
            stderr=self.stderr,
            return_code=self.return_code,
            error_kind="" if self.return_code == 0 else self.stderr or f"Exit {self.return_code}",
        )


class BiosDocumentSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="session_test_")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.nvram_path = self.root / "nvram.txt"
        self.nvram_path.write_text(SAMPLE_NVRAM, encoding="utf-8")
        self.session = BiosDocumentSession.open_file(str(self.nvram_path))

    def test_open_and_initial_state(self):
        self.assertEqual(len(self.session.document.settings), 2)
        self.assertFalse(self.session.is_dirty)
        self.assertEqual(self.session.modified_count, 0)
        self.assertTrue(self.session.document_id)

    def test_edit_numeric_and_enum(self):
        setting0 = self.session.edit(0, "42")
        self.assertEqual(setting0.current_value, "<42>")
        self.assertTrue(self.session.is_dirty)
        self.assertEqual(self.session.modified_count, 1)

        setting1 = self.session.edit(1, "02")
        self.assertEqual(setting1.current_option_id, "02")
        self.assertEqual(setting1.current_value, "Disabled")
        self.assertEqual(self.session.modified_count, 2)

    def test_numeric_draft_state(self):
        self.session.set_draft(0, True)
        self.assertTrue(self.session.is_dirty)
        self.session.set_draft(0, False)
        self.assertFalse(self.session.is_dirty)

    def test_reset_setting_to_default_and_initial(self):
        self.session.edit(0, "99")
        self.session.reset_setting(0, "default")
        self.assertEqual(self.session.document.settings[0].current_value, "<0>")

        self.session.edit(0, "99")
        self.session.reset_setting(0, "initial")
        self.assertEqual(self.session.document.settings[0].current_value, "<1>")
        self.assertFalse(self.session.is_dirty)

    def test_save_changes_creates_minimal_diff(self):
        self.session.edit(1, "02")
        out_path = str(self.root / "nvram_new.txt")

        def atomic_write(target, content):
            Path(target).write_text(content, encoding="utf-8")

        self.session.save_changes(out_path, write_fn=atomic_write)
        self.assertFalse(self.session.is_dirty)

        saved = Path(out_path).read_text(encoding="utf-8")
        doc = BiosParser().parse_file(saved)
        self.assertEqual(len(doc.settings), 1)
        self.assertEqual(doc.settings[0].name, "Boot Option")
        self.assertEqual(doc.settings[0].current_option_id, "02")

    def test_save_as_protects_live_export(self):
        self.session.edit(0, "55")
        out_path = str(self.root / "saved_copy.txt")

        def atomic_write(target, content):
            Path(target).write_text(content, encoding="utf-8")

        # Protected live export path cannot be overwritten
        with self.assertRaises(ValueError):
            self.session.save_as(
                str(self.nvram_path),
                write_fn=atomic_write,
                protected_paths=(str(self.nvram_path),),
            )

        # Non-protected path succeeds and switches session
        self.session.save_as(out_path, write_fn=atomic_write, protected_paths=(str(self.nvram_path),))
        self.assertEqual(self.session.filepath, str(Path(out_path).resolve()))
        self.assertFalse(self.session.is_dirty)


class BackupVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="vault_test_")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source.txt"
        self.source.write_text("dummy nvram content", encoding="utf-8")
        self.vault = BackupVault(self.root / "backups")

    def test_create_and_list_backups(self):
        created_path = self.vault.create_backup(str(self.source))
        self.assertTrue(Path(created_path).is_file())

        items = self.vault.list_all()
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], BackupItem)
        self.assertEqual(items[0].path, created_path)
        self.assertTrue(items[0].name.startswith("nvram_backup_"))

    def test_path_traversal_protection(self):
        outside_file = self.root / "outside.txt"
        outside_file.write_text("outside", encoding="utf-8")

        with self.assertRaises(ValueError):
            self.vault.validate_backup_path(str(outside_file))

        with self.assertRaises(ValueError):
            self.vault.delete(str(outside_file))

    def test_delete_backup(self):
        created_path = self.vault.create_backup(str(self.source))
        self.vault.delete(created_path)
        self.assertEqual(self.vault.list_all(), [])


class BiosExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="executor_test_")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.nvram_file = self.root / "nvram.txt"
        self.nvram_file.write_text(SAMPLE_NVRAM, encoding="utf-8")

        self.config = AppConfig(
            nvram_file="nvram.txt",
            nvram_new_file="nvram_new.txt",
            backup_directory="backups",
            subprocess_timeout_seconds=5,
        )
        self.service = BiosService(config=self.config, base_dir=self.root)
        self.service.check_dependencies = lambda: DependencyStatus(True, [], [], [], False)
        self.runner = FakeProcessRunner()
        self.vault = BackupVault(self.root / "backups")
        self.executor = BiosExecutor(self.service, runner=self.runner, vault=self.vault)

    def test_execute_export_creates_auto_backup(self):
        result = self.executor.execute_export("Export operation")
        self.assertTrue(result.success)
        self.assertEqual(result.action, "export")
        self.assertTrue(Path(result.backup_path).is_file())
        self.assertEqual(len(self.runner.invocations), 1)
        cmd, timeout = self.runner.invocations[0]
        self.assertIn("/o", cmd)
        self.assertEqual(timeout, 5)

    def test_execute_import_guarantees_safety_backup(self):
        new_file = self.root / "import_target.txt"
        new_file.write_text(SAMPLE_NVRAM, encoding="utf-8")

        result = self.executor.execute_import(str(new_file), "Import operation", action="import")
        self.assertTrue(result.success)
        self.assertEqual(result.action, "import")
        self.assertTrue(Path(result.backup_path).is_file())
        self.assertEqual(len(self.runner.invocations), 1)
        cmd, timeout = self.runner.invocations[0]
        self.assertIn("/i", cmd)

    def test_execute_import_fails_without_source_nvram(self):
        # Remove live nvram.txt so safety backup creation fails
        self.nvram_file.unlink()
        new_file = self.root / "import_target.txt"
        new_file.write_text(SAMPLE_NVRAM, encoding="utf-8")

        with self.assertRaises(SafetyBackupError):
            self.executor.execute_import(str(new_file))
        # Crucial invariant: Process must not be called when safety backup fails
        self.assertEqual(len(self.runner.invocations), 0)

    def test_execute_handles_runner_timeout_and_error(self):
        self.runner.raise_exc = BiosTimeoutError("Timeout")
        with self.assertRaises(BiosTimeoutError):
            self.executor.execute_export()

        self.runner.raise_exc = None
        self.runner.return_code = 1
        self.runner.stderr = "Driver access denied"
        with self.assertRaises(BiosExecutionError):
            self.executor.execute_export()


if __name__ == "__main__":
    unittest.main()
