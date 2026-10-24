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
from converter import ConversionCancelled


@unittest.skipUnless(os.name == 'nt' or os.environ.get('DISPLAY'), 'A desktop display is required')
class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = tk.Tk()
        self.app = ConverterApp(self.root)
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
        output = self.directory / 'output.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=0.3', str(source)], check=True)
        self.app.source.set(str(source))
        with patch('app.filedialog.asksaveasfilename', return_value=str(output)):
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
        with patch('app.filedialog.asksaveasfilename', return_value=str(self.directory / 'out.mp3')), patch('app.messagebox.showerror') as dialog:
            self.app.start()
            self.finish()
            dialog.assert_called_once()
        self.assertIn('Conversion failed', self.app.status.get())
        self.assertEqual(str(self.app.convert_button['state']), 'normal')
        self.app.copy_details()
        self.assertIn('existing media file', self.root.clipboard_get())

    def test_cancel_button_stops_worker_and_resets_controls(self):
        def wait_for_cancel(source, target, progress, cancel):
            cancel.wait(5)
            if cancel.is_set():
                raise ConversionCancelled()
            self.fail('Cancel was not delivered to worker')
        self.app.source.set('https://youtu.be/fixture')
        with patch('app.filedialog.asksaveasfilename', return_value=str(self.directory / 'out.mp3')), patch('app.convert', side_effect=wait_for_cancel):
            self.app.start()
            self.app.cancel_button.invoke()
            self.finish()
        self.assertIn('cancelled', self.app.status.get())
        self.assertEqual(str(self.app.cancel_button['state']), 'disabled')
        self.assertEqual(str(self.app.convert_button['state']), 'normal')
        self.assertFalse((self.directory / 'out.mp3').exists())
