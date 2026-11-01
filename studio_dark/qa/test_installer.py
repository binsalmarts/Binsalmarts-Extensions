"""Exercise restoration of real user state; never use the actual Inkscape profile."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("studio_installer", Path(__file__).resolve().parents[1] / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="studio-dark-test-")
        self.addCleanup(self.tmp.cleanup)
        self.profile = Path(self.tmp.name)
        self.prefs = self.profile / "preferences.xml"
        self.original = b'<inkscape version="1"><!-- keep --><group id="theme" gtkTheme="MacTahoe-Dark-solid" fontscale="100" iconTheme="multicolor"/><group id="ui" language="ar"/></inkscape>\n'
        self.prefs.write_bytes(self.original)
        self.css = self.profile / "ui/Studio-Dark.css"
        self.css.parent.mkdir()
        self.original_css = b'/* personal */\nbutton { border-radius: 3px; }\n'
        self.css.write_bytes(self.original_css)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.closed = mock.patch.object(installer, "ensure_closed")
        self.closed.start()
        self.addCleanup(self.closed.stop)

    def install(self, **kwargs):
        installer.install(self.profile, keep_icons=True, **kwargs)

    def test_previous_theme_css_and_preferences_restore_exactly(self):
        previous = installer.theme_target(self.profile)
        previous.mkdir(parents=True)
        (previous / "custom.txt").write_bytes(b"previous theme")
        self.install()
        self.assertIn(installer.css_block(self.profile, installer.theme_target(self.profile)), self.css.read_bytes())
        installer.uninstall(self.profile)
        self.assertEqual(self.prefs.read_bytes(), self.original)
        self.assertEqual(self.css.read_bytes(), self.original_css)
        self.assertEqual((previous / "custom.txt").read_bytes(), b"previous theme")
        self.assertTrue(list((self.profile / ".studio-dark-backups").iterdir()))

    def test_application_import_contains_only_inkscape_adjustments(self):
        self.install()
        css = self.css.read_bytes()
        self.assertIn(b"gtk-3.0/inkscape.css", css)
        self.assertNotIn(b"gtk-3.0/gtk.css", css)
        target = installer.theme_target(self.profile)
        self.assertTrue((target / "gtk-3.0/vendor/mactahoe/assets").is_dir())
        specific = (target / "gtk-3.0/inkscape.css").read_text()
        self.assertNotIn('@import url("vendor/mactahoe/gtk.css")', specific)

    def test_later_user_preferences_and_css_are_preserved(self):
        self.install()
        root = ET.fromstring(self.prefs.read_bytes())
        installer.group(root, ["ui"]).set("language", "en")
        installer.group(root, ["theme"]).set("gtkTheme", "Other-Theme")
        self.prefs.write_bytes(installer.xml_bytes(root))
        self.css.write_bytes(self.css.read_bytes() + b'label { color: white; }\n')
        installer.uninstall(self.profile)
        root = ET.fromstring(self.prefs.read_bytes())
        self.assertEqual(installer.group(root, ["ui"]).get("language"), "en")
        self.assertEqual(installer.group(root, ["theme"]).get("gtkTheme"), "Other-Theme")
        self.assertEqual(installer.group(root, ["theme"]).get("fontscale"), "100")
        self.assertEqual(self.css.read_bytes(), self.original_css + b'label { color: white; }\n')

    def test_invalid_preferences_change_nothing(self):
        self.prefs.write_bytes(b"<broken")
        with self.assertRaises(installer.InstallError):
            self.install()
        self.assertEqual(self.prefs.read_bytes(), b"<broken")
        self.assertEqual(self.css.read_bytes(), self.original_css)
        self.assertFalse((self.profile / installer.STATE_DIR).exists())

    def test_files_only_does_not_change_or_parse_preferences(self):
        self.prefs.write_bytes(b"<broken")
        self.install(files_only=True)
        installer.uninstall(self.profile)
        self.assertEqual(self.prefs.read_bytes(), b"<broken")
        self.assertEqual(self.css.read_bytes(), self.original_css)

    def test_edited_theme_is_not_deleted(self):
        self.install()
        edited = installer.theme_target(self.profile) / "gtk-3.0/gtk.css"
        edited.write_bytes(edited.read_bytes() + b"/* user change */")
        before = self.prefs.read_bytes()
        with self.assertRaises(installer.InstallError):
            installer.uninstall(self.profile)
        self.assertEqual(self.prefs.read_bytes(), before)
        self.assertIn(b"user change", edited.read_bytes())
        self.assertIn(installer.css_block(self.profile, installer.theme_target(self.profile)), self.css.read_bytes())

    def test_new_profile_uninstall_leaves_no_preferences_or_override(self):
        self.prefs.unlink()
        self.css.unlink()
        self.install()
        installer.uninstall(self.profile)
        self.assertFalse(self.prefs.exists())
        self.assertFalse(self.css.exists())

    def test_failure_writing_preferences_restores_previous_theme_and_css(self):
        atomic = installer.atomic_write
        def fail_preferences(path, data, expected):
            if path == self.prefs:
                raise OSError("simulated write failure")
            return atomic(path, data, expected)
        with mock.patch.object(installer, "atomic_write", side_effect=fail_preferences):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual(self.css.read_bytes(), self.original_css)
        self.assertEqual(self.prefs.read_bytes(), self.original)
        self.assertFalse((self.profile / installer.STATE_DIR).exists())
        self.assertFalse((installer.theme_target(self.profile)).exists())

    def test_running_default_profile_is_rejected(self):
        self.closed.stop()
        with mock.patch.object(installer, "default_profile", return_value=self.profile), mock.patch.object(installer, "inkscape_processes", return_value=["inkscape"]):
            with self.assertRaises(installer.InstallError):
                self.install()
        self.assertEqual(self.prefs.read_bytes(), self.original)
        self.assertFalse((self.profile / installer.STATE_DIR).exists())


if __name__ == "__main__":
    unittest.main()
