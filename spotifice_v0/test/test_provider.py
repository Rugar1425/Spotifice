from pathlib import Path

import Ice
from media_provider import Spotifice, main
from metadata import identify

from .icetest import IceTestCase

MEDIA = Path('test/media')


class TestProvider(IceTestCase):
    provider_port = 10000
    provider_identity = 'mediaProvider0'

    def setUp(self):
        provider_props = {
            'Spotifice.MediaProviderAdapter.Endpoints': f'tcp -p {self.provider_port}',
            'Spotifice.MediaProvider.Content': str(MEDIA),
            'Spotifice.MediaProvider.Identity': self.provider_identity
        }
        provider_strprx = f'{self.provider_identity}:tcp -p {self.provider_port} -t 500'
        self.create_server(main, provider_props)
        self.sut = self.create_proxy(provider_strprx, Spotifice.MediaProviderPrx)


class MusicLibraryTestsBase(TestProvider):
    def test_get_all_tracks(self):
        tracks = self.sut.get_all_tracks()
        self.assertEqual(len(tracks), 4)
        self.assertEqual(tracks[0].title, '1s')

    def test_get_track_info(self):
        track = self.sut.get_track_info(identify(MEDIA / '1s.mp3'))
        self.assertEqual(track.title, '1s')

    def test_track_id_does_not_depend_on_the_filename(self):
        track = self.sut.get_track_info(identify(MEDIA / '1s.mp3'))

        self.assertNotIn('1s', track.id)
        self.assertNotIn('.mp3', track.id)

    def test_get_track_info_wrong_track(self):
        with self.assertRaises(Spotifice.TrackError) as cm:
            self.sut.get_track_info('bad-track-id')

        self.assertEqual(cm.exception.item, 'bad-track-id')
        self.assertEqual(cm.exception.reason, 'Track not found')


class StreamManagerTestsBase(TestProvider):
    def test_open_stream_wrong_track(self):
        track_id = 'bad-track-id'
        render_id = self.client_ic.stringToIdentity('bad-render-id')

        with self.assertRaises(Spotifice.TrackError) as cm:
            self.sut.open_stream(render_id, track_id)

        self.assertEqual(cm.exception.item, 'bad-track-id')
        self.assertEqual(cm.exception.reason, 'Track not found')

    def test_get_audio_chunk(self):
        track_id = self.sut.get_all_tracks()[0].id
        render_id = Ice.Identity(name='fake-render-id')


        self.sut.open_stream(render_id, track_id)
        chunk = self.sut.get_chunk(render_id, 1024)

        self.assertEqual(len(chunk), 1024)
        self.assertTrue(chunk.startswith(b'OggS'))


class StreamManagerNoAuthBase(TestProvider):
    def test_get_audio_chunk_not_started_stream(self):
        render_id = Ice.Identity(name='missing-render-id')

        with self.assertRaises(Spotifice.StreamError) as cm:
            self.sut.get_chunk(render_id, 1024)

        self.assertEqual(cm.exception.item, 'missing-render-id')
        self.assertEqual(cm.exception.reason, 'No open stream for render')

    def test_open_stream_wrong_render(self):
        tracks = self.sut.get_all_tracks()
        track_id = tracks[0].id
        render_id = Ice.Identity(name='')

        with self.assertRaises(Spotifice.BadIdentity) as cm:
            self.sut.open_stream(render_id, track_id)

        self.assertEqual(cm.exception.item, '')
        self.assertEqual(cm.exception.reason, 'Invalid render identity')
