import logging

import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst  # type: ignore # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GstTranscoder")

Gst.init(None)


class TranscodeError(Exception):
    pass


class GstTranscoder:
    "Serves a track transcoded to Ogg/Opus at a fixed bitrate"

    BITRATE_KBPS = 64
    PIPELINE = ('filesrc name=src ! decodebin ! audioconvert ! audioresample ! '
                'audio/x-raw,rate=48000,channels=2 ! '
                f'opusenc bitrate={BITRATE_KBPS * 1000} ! oggmux ! '
                'appsink name=sink sync=false max-buffers=8')
    PULL_TIMEOUT = 5 * Gst.SECOND

    def __init__(self, filepath):
        self.pipeline = Gst.parse_launch(self.PIPELINE)
        self.pipeline.get_by_name('src').set_property('location', str(filepath))
        self.sink = self.pipeline.get_by_name('sink')
        self.pending = bytearray()

        self.preroll_or_fail()
        self.pipeline.set_state(Gst.State.PLAYING)

    def preroll_or_fail(self):
        self.pipeline.set_state(Gst.State.PAUSED)
        if self.pipeline.get_state(Gst.SECOND).state != Gst.State.PAUSED:
            error = self.pop_error() or "cannot decode media file"
            self.close()
            raise TranscodeError(error)

    def pop_error(self):
        message = self.pipeline.get_bus().poll(Gst.MessageType.ERROR, 0)
        return message.parse_error()[0].message if message else None

    def read(self, size):
        while len(self.pending) < size and (buffer := self.pull_buffer()):
            self.pending += buffer.extract_dup(0, buffer.get_size())

        data = bytes(self.pending[:size])
        del self.pending[:size]
        return data

    def pull_buffer(self):
        sample = self.sink.emit('try-pull-sample', self.PULL_TIMEOUT)
        if sample is not None:
            return sample.get_buffer()

        if error := self.pop_error():
            raise TranscodeError(error)
        if not self.sink.get_property('eos'):
            raise TranscodeError("timed out waiting for transcoded audio")
        return None

    def close(self):
        self.pipeline.set_state(Gst.State.NULL)
