#!/usr/bin/env python3

import logging
import queue
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from enum import Enum, auto
from time import monotonic

import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst  # type: ignore # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GstPlayer")

Gst.init(None)

state_map = {
    Gst.State.NULL: 'STOP',
    Gst.State.READY: 'STOP',
    Gst.State.PAUSED: 'PAUSED',
    Gst.State.PLAYING: 'PLAYING',
    None: 'STOP'
}

class Cmd(Enum):
    PLAY = auto()
    STOP = auto()
    PAUSE = auto()
    RESUME = auto()
    EXHAUSTED = auto()
    ABORTED = auto()
    SHUTDOWN = auto()


class GstPlayer(threading.Thread):
    CHUNK_SIZE = 4096
    PIPELINE = 'appsrc name=src ! decodebin ! audioconvert ! audioresample ! autoaudiosink'
    TIMEOUT_SECS = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.command_queue = queue.Queue()
        self.play_future: Future = None

        self.pipeline: Gst.Pipeline = None
        self.appsrc = None
        self.read_chunk = None
        self.on_track_exhausted = lambda: None

        self.show_stats = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.shutdown()
        return False

    def run(self):
        while True:
            command, args, future = self.command_queue.get()
            logger.debug(f"Processing command: {command}")
            try:
                future.set_result(self.dispatch(command, args))
            except Exception as e:
                logger.exception(f"Command {command} failed")
                future.set_exception(e)

            if command == Cmd.SHUTDOWN:
                break

    def dispatch(self, command, args):
        match command:
            case Cmd.PLAY:
                return self.activate_stream()
            case Cmd.PAUSE:
                return self.set_pipeline_state(Gst.State.PAUSED)
            case Cmd.RESUME:
                return self.set_pipeline_state(Gst.State.PLAYING)
            case Cmd.STOP | Cmd.SHUTDOWN:
                self.deactivate_stream()
                return True
            case Cmd.EXHAUSTED | Cmd.ABORTED:
                src, = args
                if src is not self.appsrc:
                    logger.debug(f"Ignoring {command.name} from a stale stream")
                    return False
                if self.deactivate_stream() and command == Cmd.EXHAUSTED:
                    threading.Thread(target=self.on_track_exhausted).start()
                return True
            case _:
                logger.warning(f"Unexpected command: {command}")
                return False

    def send_command(self, command, *args):
        future = Future()
        self.command_queue.put((command, args, future))
        return future

    def wait_result(self, future, name):
        try:
            retval = future.result(self.TIMEOUT_SECS)
        except FutureTimeoutError:
            retval = False
        logger.debug(f"{name} confirmed: {retval}")
        return retval

    def setup_pipeline(self):
        retval = Gst.parse_launch(self.PIPELINE)
        self.appsrc = retval.get_by_name('src')
        self.appsrc.set_properties(
            format=Gst.Format.BYTES, block=True, is_live=True, max_bytes=8192)
        self.appsrc.connect('need-data', self.on_need_data)
        return retval

    def activate_stream(self):
        self.last_time = None
        self.pipeline = self.setup_pipeline()
        self.pipeline.set_state(Gst.State.PLAYING)
        logger.info("Playing...")
        return True

    def deactivate_stream(self):
        if not self.pipeline:
            return False

        self.appsrc.disconnect_by_func(self.on_need_data)
        self.pipeline.set_state(Gst.State.NULL)
        self.pipeline = None
        self.appsrc = None
        logger.info("Stopped.")
        return True

    def set_pipeline_state(self, state):
        if not self.pipeline:
            return False

        retval = self.pipeline.set_state(state)
        logger.info(f"State set to {state.value_nick}: {retval.value_nick}")
        return retval != Gst.StateChangeReturn.FAILURE

    def on_need_data(self, src, length):
        assert self.read_chunk

        chunk_size = length if length > 0 else self.CHUNK_SIZE
        chunk = self.read_chunk(chunk_size)
        if chunk is None:
            logger.warning("Stream aborted: the chunk could not be read.")
            self.end_stream(src, Cmd.ABORTED)
            return
        if not chunk:
            logger.info("Stream exhausted.")
            self.end_stream(src, Cmd.EXHAUSTED)
            return

        buf = Gst.Buffer.new_allocate(None, len(chunk), None)
        buf.fill(offset=0, src=chunk)
        src.emit('push-buffer', buf)

        if self.show_stats:
            self.print_stats(len(chunk))

    def end_stream(self, src, command):
        src.emit('end-of-stream')
        self.send_command(command, src)

    def print_stats(self, chunk_size):
        if self.last_time:
            elapsed = monotonic() - self.last_time
            if elapsed > 0:
                bitrate = (chunk_size) / elapsed / 1000  # kB/s
                print(f"\rbitrate: {bitrate:.2f} kB/s    ", end='', flush=True)
        self.last_time = monotonic()

    def play(self, read_chunk, on_track_exhausted=None):
        self.read_chunk = read_chunk
        self.on_track_exhausted = on_track_exhausted or (lambda: None)
        self.play_future = self.send_command(Cmd.PLAY)

    def stop(self):
        return self.wait_result(self.send_command(Cmd.STOP), "stop")

    def pause(self):
        return self.wait_result(self.send_command(Cmd.PAUSE), "pause")

    def resume(self):
        return self.wait_result(self.send_command(Cmd.RESUME), "resume")

    def get_state(self):
        if self.pipeline is None:
            return 'STOP'

        state = self.pipeline.get_state(Gst.SECOND)
        logger.debug("{} -> {}".format(state.state.value_name, state.pending.value_name))

        return state_map.get(state.state)

    def is_playing(self):
        return self.pipeline is not None

    def confirm_play_starts(self):
        if self.play_future is None:
            return False

        return self.wait_result(self.play_future, "play")

    def shutdown(self):
        self.send_command(Cmd.SHUTDOWN)
        self.join(self.TIMEOUT_SECS)
        if self.is_alive():
            logger.warning("Failed to shutdown GstPlayer thread")
        else:
            logger.info("Shutdown complete.")
