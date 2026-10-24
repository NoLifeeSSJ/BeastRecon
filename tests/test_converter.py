import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from converter import convert


class ConversionTests(unittest.TestCase):
    def test_roundtrip_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'tone.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.3', str(source)], check=True)
            mp3 = convert(str(source), root / 'tone.mp3')
            video = convert(str(mp3), root / 'tone.mp4')
            extracted = convert(str(video), root / 'extracted.mp3')
            for path in (mp3, video, extracted):
                data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)]))
                self.assertTrue(any(s['codec_type'] == 'audio' for s in data['streams']))
            self.assertTrue(any(s['codec_type'] == 'video' for s in json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(video)]))['streams']))
            before = mp3.read_bytes()
            with self.assertRaises(ValueError):
                convert(str(source), mp3)
            self.assertEqual(before, mp3.read_bytes())

    def test_invalid_input_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'output.mp3'
            with self.assertRaises(ValueError):
                convert(str(Path(directory) / 'missing.wav'), target)
            self.assertFalse(target.exists())
