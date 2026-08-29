"""Download the map tiles the app needs into web/tiles/, so the map works offline.

Skips tiles already on disk, so re-running is cheap. Delete web/tiles/ (or run
`make clean-tiles`) after changing tile_version in tables/map_config.json.
"""
import os
import sys
import time
import urllib.error
import urllib.request

from . import grid

UA = {'User-Agent': 'osrs-port-tasks-local/0.1'}
PAUSE = 0.05  # be gentle with the wiki's tile server


def main():
    cfg = grid.config()
    zooms = [int(z) for z in sys.argv[1:]] or cfg['zooms']
    b = grid.bounds(cfg)

    got = skipped = missing = 0
    for z in zooms:
        level = b['zooms'][z]
        os.makedirs(grid.TILE_ROOT / str(z), exist_ok=True)
        for x in range(level['tx'][0], level['tx'][1] + 1):
            for y in range(level['ty'][0], level['ty'][1] + 1):
                path = grid.tile_path(z, x, y)
                if os.path.exists(path):
                    skipped += 1
                    continue
                url = grid.tile_url(cfg, z, x, y)
                try:
                    req = urllib.request.Request(url, headers=UA)
                    data = urllib.request.urlopen(req, timeout=30).read()
                except urllib.error.HTTPError as e:
                    # open ocean has no rendered tile; that is normal, not an error
                    if e.code == 404:
                        missing += 1
                        continue
                    raise
                open(path, 'wb').write(data)
                got += 1
                time.sleep(PAUSE)
        print(f'  zoom {z}: done')

    size = sum(os.path.getsize(os.path.join(d, f))
               for d, _, fs in os.walk(grid.TILE_ROOT) for f in fs)
    print(f'{got} downloaded, {skipped} already present, {missing} blank (404). '
          f'web/tiles is {size / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
