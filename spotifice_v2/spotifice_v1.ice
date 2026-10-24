[["underscore"]]
#include <Ice/Identity.ice>

module Spotifice {
    class TrackInfo {
        string id;
        string title;
    };

    sequence<byte> AudioChunk;
    sequence<TrackInfo> TrackInfoSeq;

    exception Error {
        optional(1) string item;
        string reason;
    };

    exception IOError extends Error{};
    exception BadIdentity extends Error{};
    exception BadReference extends Error{};
    exception PlayerError extends Error{};
    exception StreamError extends Error{};
    exception TrackError extends Error{};

    interface MusicLibrary {
        idempotent TrackInfoSeq get_all_tracks() throws IOError;
        idempotent TrackInfo get_track_info(string track_id) throws IOError, TrackError;
    };

    interface StreamManager {
        idempotent void open_stream(Ice::Identity media_render_id, string track_id)
            throws BadIdentity, IOError, TrackError;
        idempotent void close_stream(Ice::Identity media_render_id);
        AudioChunk get_chunk(Ice::Identity media_render_id, int chunk_size)
            throws IOError, StreamError;
    };

    interface MediaProvider extends MusicLibrary, StreamManager {};

    // new in version 1
    enum PlaybackState {
        PLAYING,
        PAUSED,
        STOPPED
    };

    // new in version 1
    class PlaybackStatus {
        PlaybackState state;
        TrackInfo current_track;
        bool is_repeating;
    };

    interface RenderConnectivity {
        idempotent void bind_media_provider(MediaProvider* media_provider) throws BadReference;
        idempotent void unbind_media_provider();
    };

    interface ContentManager {
        idempotent void load_track(string track_id)
            throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent TrackInfo get_current_track();
    };

    interface PlaybackController {
        void play() throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent void stop() throws PlayerError;
        
        // new in version 1
        idempotent void pause() throws PlayerError;
        idempotent PlaybackStatus get_status();
        void previous() throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent void set_repeat(bool enabled);
    };

    interface MediaRender extends RenderConnectivity, ContentManager, PlaybackController {};
};
