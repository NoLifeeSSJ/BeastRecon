"""Desktop integration checks; run under a display (for example Xvfb on Linux)."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from app import ConverterApp
from converter import ConversionCancelled, MediaInfo
from preferences import Preferences, save_preferences


@unittest.skipUnless(os.name == 'nt' or os.environ.get('DISPLAY'), 'A desktop display is required')
class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.downloads = self.directory / 'downloads'
        self.preferences_file = self.directory / 'preferences.json'
        save_preferences(Preferences(str(self.downloads), 'mp3', False), self.preferences_file)
        self.root = tk.Tk()
        self.app = ConverterApp(self.root, self.preferences_file)
        self.addCleanup(self.app.destroy)
        self.root.update()

    def finish(self):
        deadline = time.monotonic() + 10
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app.busy, 'Desktop conversion worker did not finish')

    def test_convert_then_play_and_open_folder(self):
        source = self.directory / 'input.wav'
        output = self.downloads / 'input.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=0.3', str(source)], check=True)
        self.app.source.set(str(source))
        with patch('app.filedialog.asksaveasfilename', side_effect=AssertionError('Download must not prompt for a filename')):
            self.app.convert_button.invoke()
        self.finish()
        self.assertTrue(output.is_file())
        self.assertIn('Saved:', self.app.status.get())
        self.assertEqual(str(self.app.play_button['state']), 'normal')
        self.assertEqual(float(self.app.bar['value']), 100)
        with patch('app.open_result') as open_result:
            self.app.play_button.invoke()
            open_result.assert_called_with(output, False)
            self.app.folder_button.invoke()
            open_result.assert_called_with(output, True)

    def test_failure_details_can_be_copied_and_retry_enabled(self):
        self.app.source.set(str(self.directory / 'missing.wav'))
        with patch('app.messagebox.showerror') as dialog:
            self.app.start()
            self.finish()
            dialog.assert_called_once()
        self.assertIn('Conversion failed', self.app.status.get())
        self.assertEqual(str(self.app.convert_button['state']), 'normal')
        self.app.copy_details()
        self.assertIn('existing media file', self.root.clipboard_get())

    def test_cancel_button_stops_worker_and_resets_controls(self):
        def wait_for_cancel(source, directory, extension, progress, cancel, on_metadata):
            cancel.wait(5)
            if cancel.is_set():
                raise ConversionCancelled()
            self.fail('Cancel was not delivered to worker')
        self.app.source.set('https://youtu.be/fixture')
        with patch('app.convert_to_folder', side_effect=wait_for_cancel):
            self.app.start()
            self.app.cancel_button.invoke()
            self.finish()
        self.assertIn('cancelled', self.app.status.get())
        self.assertEqual(str(self.app.cancel_button['state']), 'disabled')
        self.assertEqual(str(self.app.convert_button['state']), 'normal')
        self.assertFalse(self.downloads.exists())

    def wait_preview(self):
        deadline = time.monotonic() + 5
        while (self.app.preview_running or self.app.preview_timer is not None) and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app.preview_running)

    def test_version_and_combined_preferences_about_changelog(self):
        self.assertIn('V1.1', self.root.title())
        self.app.show_settings()
        self.assertEqual([self.app.settings_notebook.tab(tab, 'text') for tab in self.app.settings_notebook.tabs()],
                         ['Preferences', 'About', 'Changelog'])
        new_directory = self.directory / 'my music'
        self.app.pref_directory.set(str(new_directory))
        self.app.pref_format.set('flac')
        self.app.pref_preview.set(True)
        self.app.save_preference_changes()
        self.assertIn(str(new_directory), self.app.save_folder.get())
        other_root = tk.Toplevel(self.root)
        other_app = ConverterApp(other_root, self.preferences_file)
        self.addCleanup(other_app.destroy)
        self.assertEqual(other_app.preferences.download_directory, str(new_directory))
        self.assertEqual(other_app.output_format.get(), 'flac')
        self.assertTrue(other_app.preferences.auto_preview)

    def test_background_preview_shows_title_creator_and_duration(self):
        self.app.source.set('https://youtu.be/fixture')
        with patch('app.inspect_media', return_value=MediaInfo('Test Song', 'Test Artist', 125)) as inspect:
            self.app.begin_preview()
            self.wait_preview()
        self.assertIn('Test Song', self.app.preview.get())
        self.assertIn('Test Artist', self.app.preview.get())
        self.assertIn('2:05', self.app.preview.get())
        inspect.assert_called_once()
        self.assertFalse(self.downloads.exists())

    def test_automatic_preview_waits_for_typing_and_can_be_disabled(self):
        self.app.apply_preferences(Preferences(str(self.downloads), 'mp3', True))
        with patch('app.inspect_media', return_value=MediaInfo('Auto title')) as inspect:
            self.app.source.set('https://youtu.be/fixture')
            inspect.assert_not_called()
            self.wait_preview()
            inspect.assert_called_once()
        self.assertIn('Auto title', self.app.preview.get())
        self.app.apply_preferences(Preferences(str(self.downloads), 'mp3', False))
        self.app.source.set('https://youtu.be/another')
        self.assertIsNone(self.app.preview_timer)

    def test_old_preview_does_not_replace_new_link_title(self):
        self.app.source.set('https://youtu.be/old')
        old_generation = self.app.preview_generation
        self.app.source.set('https://youtu.be/new')
        self.app.show_media_info(MediaInfo('New song'))
        self.app.finish_preview(old_generation, 'https://youtu.be/old', MediaInfo('Old song'), None)
        self.assertIn('New song', self.app.preview.get())
        self.assertNotIn('Old song', self.app.preview.get())

    def test_incomplete_link_preview_does_not_break_the_ui(self):
        self.app.source.set('https://[')
        self.app.begin_preview()
        self.assertIn('complete media URL', self.app.preview.get())
        self.assertFalse(self.app.preview_running)
