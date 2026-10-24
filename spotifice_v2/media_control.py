#!/usr/bin/env python3

import sys
from time import sleep

import Ice

Ice.loadSlice(f'-I{Ice.getSliceDir()} spotifice_v2.ice')
import Spotifice  # type: ignore # noqa: E402


def get_proxy(ic, property, cls):
    proxy = ic.propertyToProxy(property)

    for _ in range(5):
        try:
            proxy.ice_ping()
            break
        except Ice.ConnectionRefusedException:
            sleep(0.5)

    object = cls.checkedCast(proxy)
    if object is None:
        raise RuntimeError(f'Invalid proxy for {property}')

    return object


def main(ic):
    provider = get_proxy(ic, 'Spotifice.MediaProvider.Proxy', Spotifice.MediaProviderPrx)
    render = get_proxy(ic, 'Spotifice.MediaRender.Proxy', Spotifice.MediaRenderPrx)

    print("Fetching all tracks...")
    tracks = provider.get_all_tracks()
    for t in tracks:
        print(f"- {t.title}")

    if not tracks:
        print("No tracks found.")
        return

    print(f"Requesting info for track {tracks[0].id}")
    print(f"Track title: {tracks[0].title}")

    playlists = provider.get_all_playlists()

    for p in playlists:
        print(f"-{p.name}({p.id})")

    render.bind_media_provider(provider)
    render.load_playlist(playlists[0].id)
    render.play()
    render.next()
    render.stop()
    render.previous()
    render.play()
    render.set_repeat(enabled = True)
    render.next()
    render.next()
    print(f"Finaliza")



if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("Usage: media_control.py --Ice.Config=<config-file>")

    with Ice.initialize(sys.argv) as communicator:
        main(communicator)
