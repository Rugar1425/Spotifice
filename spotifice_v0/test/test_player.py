import threading
from time import monotonic, sleep
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock

from gst_player import Cmd, GstPlayer

TRACK = Path('test/media/1s.mp3')


class TestPlayerExhausted(TestCase):
    def setUp(self):
        self.sut = GstPlayer()
        self.sut.start()
        self.addCleanup(self.sut.shutdown)

    def play(self, on_track_exhausted=None):
        track = TRACK.open('rb')
        self.addCleanup(track.close)
        self.sut.play(track.read, on_track_exhausted)
        self.assertTrue(self.sut.confirm_play_starts())

    def test_exhausted_stops_current_stream(self):
        exhausted = threading.Event()
        self.play(exhausted.set)

        future = self.sut.send_command(Cmd.EXHAUSTED, self.sut.appsrc)

        self.assertTrue(future.result(GstPlayer.TIMEOUT_SECS))
        self.assertFalse(self.sut.is_playing())
        self.assertTrue(exhausted.wait(GstPlayer.TIMEOUT_SECS))

    def test_stale_exhausted_does_not_stop_new_stream(self):
        self.play()
        stale_src = self.sut.appsrc
        self.assertTrue(self.sut.stop())

        on_track_exhausted = Mock()
        self.play(on_track_exhausted)

        future = self.sut.send_command(Cmd.EXHAUSTED, stale_src)

        self.assertFalse(future.result(GstPlayer.TIMEOUT_SECS))
        self.assertTrue(self.sut.is_playing())
        on_track_exhausted.assert_not_called()

    def test_exhausted_after_stop_is_ignored(self):
        on_track_exhausted = Mock()
        self.play(on_track_exhausted)
        stale_src = self.sut.appsrc
        self.assertTrue(self.sut.stop())

        future = self.sut.send_command(Cmd.EXHAUSTED, stale_src)

        self.assertFalse(future.result(GstPlayer.TIMEOUT_SECS))
        on_track_exhausted.assert_not_called()


class TestPlayerAborted(TestCase):
    def setUp(self):
        self.sut = GstPlayer()
        self.sut.start()
        self.addCleanup(self.sut.shutdown)

    def test_aborted_stops_without_notifying_exhausted(self):
        track = TRACK.open('rb')
        self.addCleanup(track.close)
        on_track_exhausted = Mock()
        self.sut.play(track.read, on_track_exhausted)
        self.assertTrue(self.sut.confirm_play_starts())

        future = self.sut.send_command(Cmd.ABORTED, self.sut.appsrc)

        self.assertTrue(future.result(GstPlayer.TIMEOUT_SECS))
        self.assertFalse(self.sut.is_playing())
        on_track_exhausted.assert_not_called()

    def test_failing_read_chunk_aborts_stream(self):
        on_track_exhausted = Mock()
        self.sut.play(lambda _: None, on_track_exhausted)
        self.assertTrue(self.sut.confirm_play_starts())

        deadline = monotonic() + GstPlayer.TIMEOUT_SECS
        while self.sut.is_playing() and monotonic() < deadline:
            sleep(0.05)

        self.assertFalse(self.sut.is_playing())
        on_track_exhausted.assert_not_called()
