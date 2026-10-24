from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from preferences import Preferences, load_preferences, save_preferences
from converter import safe_filename, unique_destination


class PreferenceAndFilenameTests(unittest.TestCase):
    def test_preferences_survive_reload_and_failed_atomic_save(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'settings/preferences.json'
            first = Preferences(str(root / 'Music'), 'm4a', False)
            save_preferences(first, path)
            self.assertEqual(load_preferences(path), (first, None))
            before = path.read_bytes()
            with patch('preferences.os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    save_preferences(Preferences(str(root / 'Other')), path)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(list(path.parent.glob('.preferences-*.tmp')))

    def test_corrupt_preferences_do_not_crash_or_destroy_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preferences.json'
            path.write_text('invalid JSON', encoding='utf-8')
            preferences, warning = load_preferences(path)
            self.assertEqual(preferences.default_format, 'mp3')
            self.assertIsNotNone(warning)
            self.assertEqual(path.read_text(), 'invalid JSON')

    def test_windows_filenames_remain_readable_and_safe(self):
        for title in ('../folder/Test: song?*', 'CON', 'NUL.mp3', 'COM1', 'LPT³', ' . ', 'Song. ', '🎵 café' * 100):
            with self.subTest(title=title):
                filename = safe_filename(title)
                self.assertNotRegex(filename, r'[<>:"/\\|?*\x00-\x1f]')
                self.assertFalse(filename.endswith((' ', '.')))
                self.assertGreater(len(filename), 0)
                self.assertLessEqual(len(filename.encode('utf-8')), 161)
        self.assertEqual(safe_filename('Café Song 🎵'), 'Café Song 🎵')
        self.assertEqual(safe_filename('CON'), '_CON')

    def test_duplicate_names_are_numbered_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'Song.mp3').write_text('keep me')
            (root / 'Song (2).mp3').write_text('keep me too')
            self.assertEqual(unique_destination(root, 'Song', 'mp3').name, 'Song (3).mp3')
            self.assertEqual((root / 'Song.mp3').read_text(), 'keep me')
