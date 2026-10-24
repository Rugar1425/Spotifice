from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock

from gst_transcoder import GstTranscoder, TranscodeError

TRACK = Path('test/media/2s.mp3')
CHUNK_SIZE = 4096


class TestTranscoder(TestCase):
    def setUp(self):
        self.sut = GstTranscoder(TRACK)
        self.addCleanup(self.sut.close)

    def test_output_is_ogg(self):
        self.assertTrue(self.sut.read(CHUNK_SIZE).startswith(b'OggS'))

    def test_reads_empty_at_the_end_of_the_track(self):
        while self.sut.read(CHUNK_SIZE):
            pass

        self.assertEqual(self.sut.read(CHUNK_SIZE), b'')

    def test_output_is_about_64_kbps(self):
        total = 0
        while chunk := self.sut.read(CHUNK_SIZE):
            total += len(chunk)

        kbps = total * 8 / 2 / 1000
        self.assertLess(kbps, 90)

    def test_a_stalled_source_is_an_error_not_the_end_of_the_track(self):
        self.sut.sink = Mock(**{'emit.return_value': None, 'get_property.return_value': False})

        with self.assertRaises(TranscodeError):
            self.sut.read(CHUNK_SIZE)

    def test_unreadable_file_is_an_error(self):
        with self.assertRaises(TranscodeError):
            GstTranscoder(Path('test/media/missing.mp3'))
