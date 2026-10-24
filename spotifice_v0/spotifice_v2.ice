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
    exception PlaylistError extends Error{};  // new in version 2

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

    // new in version 2
    sequence<string> TrackIdSeq;

    // new in version 2
    class Playlist {
        string id;
        string name;
        string description;
        string owner;
        long created_at;
        TrackIdSeq track_ids;
    };

    // new in version 2
    sequence<Playlist> PlaylistSeq;

    // new in version 2
    interface PlaylistManager {
        idempotent PlaylistSeq get_all_playlists();
        idempotent Playlist get_playlist(string playlist_id) throws PlaylistError;
    };

    // changed in version 2
    interface MediaProvider extends MusicLibrary, PlaylistManager, StreamManager {};

    interface RenderConnectivity {
        idempotent void bind_media_provider(MediaProvider* media_provider) throws BadReference;
        idempotent void unbind_media_provider();
    };

    interface ContentManager {
        idempotent void load_track(string track_id)
            throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent TrackInfo get_current_track();

        // new in version 2
        idempotent void load_playlist(string playlist_id)
            throws BadReference, IOError, PlayerError, PlaylistError, StreamError, TrackError;
    };

    interface PlaybackController {
        void play() throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent void stop() throws PlayerError;

        // new in version 2
        void next() throws BadReference, IOError, PlayerError, StreamError, TrackError;
        void previous() throws BadReference, IOError, PlayerError, StreamError, TrackError;
        idempotent void set_repeat(bool enabled);
    };

    interface MediaRender extends RenderConnectivity, ContentManager, PlaybackController {};
};
