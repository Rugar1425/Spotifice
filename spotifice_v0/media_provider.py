#!/usr/bin/env python3

import logging
import signal
import sys
import threading
import uuid
from collections import namedtuple
from pathlib import Path
from time import sleep

import Ice
from Ice import identityToString as id2str

import metadata
from gst_transcoder import GstTranscoder

Ice.loadSlice(f'-I{Ice.getSliceDir()} spotifice_v0.ice')
import Spotifice  # type: ignore # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MediaProvider")

LocalTrack = namedtuple('LocalTrack', 'info path')


class StreamedFile:
    def __init__(self, track_info, filepath):
        self.track = track_info

        try:
            self.transcoder = GstTranscoder(filepath)
        except Exception as e:
            raise Spotifice.IOError(track_info.id, f"Error opening media file: {e}")

    def read(self, size):
        return self.transcoder.read(size)

    def close(self):
        try:
            self.transcoder.close()
        except Exception as e:
            logger.error(f"Error closing file for track '{self.track.id}': {e}")

    def __repr__(self):
        return f"<StreamState '{self.track.id}'>"


class MediaProviderI(Spotifice.MediaProvider):
    def __init__(self, media_dir):
        self.media_dir = Path(media_dir)
        self.tracks = {}  # track_id -> LocalTrack
        self.active_streams = {}  # media_render_id -> StreamedFile
        self.load_media()

    def get_track(self, track_id):
        try:
            return self.tracks[track_id]
        except KeyError:
            raise Spotifice.TrackError(track_id, "Track not found")

    def load_media(self):
        for filepath in sorted(Path(self.media_dir).iterdir()):
            if not filepath.is_file() or filepath.suffix.lower() != ".mp3":
                continue

            try:
                info = self.track_info(filepath)
            except metadata.UnreadableFile as e:
                logger.warning(f"Skipping '{filepath.name}': {e}")
                continue

            self.tracks[info.id] = LocalTrack(info, filepath)

        logger.info(f"Load media:  {len(self.tracks)} tracks")

    @staticmethod
    def track_info(filepath):
        return Spotifice.TrackInfo(
            id=metadata.identify(filepath),
            title=metadata.title(filepath))

    # ---- MusicLibrary ----
    def get_all_tracks(self, current=None):
        return [each.info for each in self.tracks.values()]

    def get_track_info(self, track_id, current=None):
        return self.get_track(track_id).info

    # ---- StreamManager ----
    def open_stream(self, render_id, track_id, current=None):
        str_render_id = id2str(render_id)
        track = self.get_track(track_id)

        if not render_id.name:
            raise Spotifice.BadIdentity(str_render_id, "Invalid render identity")

        self.close_stream(render_id, current)
        self.active_streams[str_render_id] = StreamedFile(track.info, track.path)

        logger.info("Open stream for track '{}' on render '{}'".format(
            track.info.title, str_render_id))

    def close_stream(self, render_id, current=None):
        str_render_id = id2str(render_id)
        if stream_state := self.active_streams.pop(str_render_id, None):
            stream_state.close()
            logger.info(f"Closed stream for render '{str_render_id}'")

    def get_chunk(self, render_id, chunk_size, current=None):
        str_render_id = id2str(render_id)
        try:
            streamed_file = self.active_streams[str_render_id]
        except KeyError:
            raise Spotifice.StreamError(str_render_id, "No open stream for render")

        try:
            data = streamed_file.read(chunk_size)
            if not data:
                logger.info(f"Track exhausted: '{streamed_file.track.title}'")
                self.close_stream(render_id, current)
            return data

        except Exception as e:
            raise Spotifice.IOError(
                streamed_file.track.id, f"Error reading file: {e}")


def shutdown_on_interrupt(ic):
    def shutdown(*_):
        ic.shutdown()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT,  shutdown)
        signal.signal(signal.SIGTERM, shutdown)


def main(ic):
    shutdown_on_interrupt(ic)

    properties = ic.getProperties()
    identity = properties.getPropertyWithDefault(
        'Spotifice.MediaProvider.Identity',  str(uuid.uuid1()))
    media_dir = properties.getPropertyWithDefault(
        'Spotifice.MediaProvider.Content', 'media')
    servant = MediaProviderI(Path(media_dir))

    adapter = ic.createObjectAdapter("Spotifice.MediaProviderAdapter")
    proxy = adapter.add(servant, ic.stringToIdentity(identity))
    logger.info(f"MediaProvider: {proxy}")

    adapter.activate()

    while not ic.isShutdown():
        sleep(0.5)

    logger.info("Server shutdown")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: media_provider.py --Ice.Config=<config-file>")

    with Ice.initialize(sys.argv) as communicator:
        main(communicator)
