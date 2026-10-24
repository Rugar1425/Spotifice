#!/usr/bin/env python3

import logging
import signal
import sys
import threading
import uuid
from contextlib import contextmanager
from time import sleep

import Ice
from Ice import identityToString as id2str

from gst_player import GstPlayer

Ice.loadSlice(f'-I{Ice.getSliceDir()} spotifice_v1.ice')
import Spotifice  # type: ignore # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MediaRender")


class MediaRenderI(Spotifice.MediaRender):
    def __init__(self, player):
        self.player = player
        self.provider = None
        self.current_track = None
        self.is_repeating = False
        self.playback_state = Spotifice.PlaybackState.STOPPED
        self.tracks_history = []

    def ensure_player_stopped(self):
        if self.player.is_playing():
            raise Spotifice.PlayerError(reason="Already playing")

    def ensure_provider_bound(self):
        if not self.provider:
            raise Spotifice.BadReference(reason="No MediaProvider bound")

    # --- RenderConnectivity ---

    def bind_media_provider(self, media_provider, current=None):
        try:
            proxy = media_provider.ice_timeout(500)
            proxy.ice_ping()
        except Ice.ConnectionRefusedException as e:
            raise Spotifice.BadReference(reason=f"MediaProvider not reachable: {e}")

        self.provider = media_provider
        logger.info(f"Bound to MediaProvider '{id2str(media_provider.ice_getIdentity())}'")

    def unbind_media_provider(self, current=None):
        try:
            self.stop(current)
        except Spotifice.PlayerError as e:
            logger.error(f"Unbinding despite stop failure: {e.reason}")

        self.provider = None
        logger.info("Unbound MediaProvider")

    # --- ContentManager ---

    def load_track(self, track_id, current=None):
        self.ensure_provider_bound()

        logger.info(f"Solicitando información de la canción: {track_id}")

        try:
            with self.previous_state(current):
                track = self.provider.get_track_info(track_id)
                self.current_track = track
                self.tracks_history.append(track)

            logger.info(f"Current track set to: {self.current_track.title}")

        except Spotifice.TrackError as e:
            logger.error(f"Error setting track: {e.reason}")
            raise

    def get_current_track(self, current=None):
        return self.current_track

    # --- PlaybackController ---

    @contextmanager
    def previous_state(self, current):
        playing = self.playback_state
        if playing == Spotifice.PlaybackState.PLAYING:
            self.stop(current)
        try:
            yield
        finally:
            if playing == Spotifice.PlaybackState.PLAYING:
                self.play(current)
            if playing == Spotifice.PlaybackState.PAUSED:
                self.play(current)
                self.pause(current)

    def play(self, current=None):
        assert current, "remote invocation required"

        self.ensure_provider_bound()

        if not self.current_track:
            raise Spotifice.TrackError(reason="No track loaded")

        try:
            self.provider.open_stream(current.id, self.current_track.id)
        except Spotifice.BadIdentity as e:
            logger.error(f"Error starting stream: {e.reason}")
            raise Spotifice.StreamError(reason="Strean setup failed")

        match self.playback_state:
            case Spotifice.PlaybackState.PLAYING:
                raise Spotifice.PlayerError(reason="Already playing")
            case Spotifice.PlaybackState.PAUSED: 
                self.player.play(self.chunk_reader(current.id, current))
            case Spotifice.PlaybackState.STOPPED:
                self.player.play(self.chunk_reader(current.id, current))
        
        if not self.player.confirm_play_starts():
            raise Spotifice.PlayerError(reason="Failed to confirm playback")
        
        self.playback_state = Spotifice.PlaybackState.PLAYING

    def chunk_reader(self, render_id, current):
        provider = self.provider

        def read_chunk(chunk_size):
            try:
                data = provider.get_chunk(render_id, chunk_size)
                if not data:
                    self.on_track_exhaust(current)
                return data
            except Spotifice.IOError as e:
                logger.error(f"Playback of track '{e.item}' aborted: {e.reason}")
            except Ice.Exception as e:
                logger.critical(e)

        return read_chunk

    def on_track_exhaust(self, current):
        self.playback_state = Spotifice.PlaybackState.STOPPED
        if (self.is_repeating):
            self.play(current)

    def stop(self, current=None):
        if self.provider and current:
            self.provider.close_stream(current.id)
            self.playback_state = Spotifice.PlaybackState.STOPPED

        if not self.player.stop():
            raise Spotifice.PlayerError(reason="Failed to confirm stop")

        logger.info("Stopped")

    def get_status(self, current=None):
        return Spotifice.PlaybackStatus(
            state = self.playback_state,
            current_track = self.current_track,
            is_repeating = self.is_repeating
        )
    
    def set_repeat(self, enabled, current=None):
        self.is_repeating = enabled
        logger.info(f"Set repeat: {enabled}")

    def pause(self, current=None):

        if self.playback_state == Spotifice.PlaybackState.STOPPED:
            raise Spotifice.PlayerError(reason="Cannot pause when stopped")
        self.playback_state = Spotifice.PlaybackState.PAUSED
        
    def previous(self, current=None):
        try:
            self.tracks_history.pop()
            self.load_track(self.tracks_history.pop().id, current)
            logger.info(f"Current track: {self.current_track.title}")
            if self.playback_state == Spotifice.PlaybackState.PLAYING:
                logger.info(f"Playback state: {self.playback_state}")
                self.pause(current)
                logger.info(f"Playback state: {self.playback_state}")
                self.play(current)

        except Exception as e:
            raise Spotifice.TrackError(f"Error no tracks: {e}")

def shutdown_on_interrupt(ic):
    def shutdown(*_):
        ic.shutdown()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT,  shutdown)
        signal.signal(signal.SIGTERM, shutdown)


def main(ic, player):
    shutdown_on_interrupt(ic)

    servant = MediaRenderI(player)

    properties = ic.getProperties()
    identity = properties.getPropertyWithDefault(
        'Spotifice.MediaRender.Identity',  str(uuid.uuid1()))

    adapter = ic.createObjectAdapter('Spotifice.MediaRenderAdapter')
    proxy = adapter.add(servant, ic.stringToIdentity(identity))
    logger.info(f"MediaRender: {proxy}")

    adapter.activate()
    while not ic.isShutdown():
        sleep(0.5)

    logger.info("Server shutdown.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: media_render.py --Ice.Config=<config-file>")

    with Ice.initialize(sys.argv) as communicator, GstPlayer() as player:
        main(communicator, player)
