"""Download the map tiles the app needs into tiles/, so the map works offline.

Skips tiles already on disk, so re-running is cheap. Delete tiles/ (or run
`make clean-tiles`) after changing tile_version in map_config.json.
"""
import os, sys, time, urllib.error, urllib.request
import mapdata

UA = {'User-Agent': 'osrs-port-tasks-local/0.1'}
PAUSE = 0.05  # be gentle with the wiki's tile server


def main():
    cfg = mapdata.config()
    zooms = [int(z) for z in sys.argv[1:]] or cfg['zooms']
    b = mapdata.bounds(cfg)

    got = skipped = missing = 0
    for z in zooms:
        grid = b['zooms'][z]
        os.makedirs(f'{mapdata.TILE_DIR}/{z}', exist_ok=True)
        for x in range(grid['tx'][0], grid['tx'][1] + 1):
            for y in range(grid['ty'][0], grid['ty'][1] + 1):
                path = mapdata.tile_path(z, x, y)
                if os.path.exists(path):
                    skipped += 1
                    continue
                url = mapdata.tile_url(cfg, z, x, y)
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
               for d, _, fs in os.walk(mapdata.TILE_DIR) for f in fs)
    print(f'{got} downloaded, {skipped} already present, {missing} blank (404). '
          f'tiles/ is {size / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
