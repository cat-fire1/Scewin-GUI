"""Tests for BackupVault and BackupItem."""

import tempfile
import time
from pathlib import Path
import unittest

from scewin_gui.core import BackupVault


class TestBackupVault(unittest.TestCase):
    def test_backup_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            backup_dir = Path(tmp_dir) / "backups"
            vault = BackupVault(backup_dir)

            source = Path(tmp_dir) / "source_nvram.txt"
            source.write_text("Setup Question = Sample", encoding="utf-8")

            # Create first backup
            b1 = vault.create_backup(str(source))
            self.assertTrue(Path(b1).is_file())

            time.sleep(0.01)

            # Create second backup
            b2 = vault.create_backup(str(source))
            self.assertTrue(Path(b2).is_file())

            # List all
            items = vault.list_all()
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].path, b2)
            self.assertEqual(items[1].path, b1)

            # Validate path
            validated = vault.validate_backup_path(b1)
            self.assertEqual(str(validated), b1)

            # Delete
            vault.delete(b1)
            self.assertEqual(len(vault.list_all()), 1)

    def test_delete_outside_backup_dir_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            backup_dir = Path(tmp_dir) / "backups"
            vault = BackupVault(backup_dir)
            outside_file = Path(tmp_dir) / "outside.txt"
            outside_file.write_text("Critical file", encoding="utf-8")

            with self.assertRaises(ValueError):
                vault.delete(str(outside_file))


if __name__ == "__main__":
    unittest.main()
