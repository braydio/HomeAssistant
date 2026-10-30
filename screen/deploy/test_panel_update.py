"""Hardware-independent checks for the Screen auto-update staging logic."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parent / "panel-update.py"
spec = importlib.util.spec_from_file_location("panel_update", MODULE)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class UpdaterTests(unittest.TestCase):
    def test_hashes_only_regular_python_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "panel.py").write_text("print('ok')\n")
            (root / "config.json").write_text('{"token": "LOCAL_ONLY"}')
            (root / "notes.txt").write_text("left alone")
            self.assertEqual(list(updater.hashes(root)), ["panel.py"])

    def test_stage_keeps_local_config_and_removes_old_module(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / "current"
            old.mkdir()
            (old / "panel.py").write_text("print('old')\n")
            (old / "obsolete.py").write_text("print('obsolete')\n")
            (old / "config.json").write_text('{"camera_entities": ["camera.actual"]}')
            source = root / "source"
            source.mkdir()
            (source / "panel.py").write_text("print('new')\n")
            (source / "test_ui_offscreen.py").write_text("pass\n")
            work = root / "work"
            work.mkdir()
            with patch.object(updater, "APP", old), patch.object(updater, "command", return_value=""):
                candidate = updater.stage(source, work)
                self.assertEqual((candidate / "panel.py").read_text(), "print('new')\n")
                self.assertFalse((candidate / "obsolete.py").exists())
                self.assertEqual((candidate / "config.json").read_text(),
                                 '{"camera_entities": ["camera.actual"]}')

    def test_install_does_not_modify_stopped_screen(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "current"
            original.mkdir()
            (original / "panel.py").write_text("old")
            staged = root / "candidate"
            staged.mkdir()
            (staged / "panel.py").write_text("new")
            with patch.object(updater, "APP", original), patch.object(updater, "BACKUPS", root / "backups"), \
                 patch.object(updater, "processes", return_value=([], [])):
                self.assertFalse(updater.install_release(staged, "a" * 40))
                self.assertEqual((original / "panel.py").read_text(), "old")
                self.assertTrue(staged.exists())


if __name__ == "__main__":
    unittest.main()
