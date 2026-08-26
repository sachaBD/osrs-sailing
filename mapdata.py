"""Shared tile-grid maths for the map: config, bounds, tile URLs."""
import json
import locations

CONFIG = 'map_config.json'
TILE_DIR = 'tiles'
TILE_PX = 256  # every rendered tile image is 256x256


def config(path=CONFIG):
    return json.load(open(path))


def port_coords(meta=None):
    meta = meta or locations.load()
    out = {}
    for name, v in meta.items():
        if v.get('coords'):
            x, y = v['coords'].split(',')
            out[name] = (int(x), int(y))
    return out


def bounds(cfg=None, coords=None):
    """Tile index ranges per zoom, plus the game-space origin the app draws from.

    A tile at zoom z spans TILE_PX/2**z game tiles, so zoom 0 tiles are the
    coarsest grid and every finer level nests inside them exactly.
    """
    cfg = cfg or config()
    coords = coords or port_coords()
    pad = cfg['padding']
    xs = [p[0] for p in coords.values()]
    ys = [p[1] for p in coords.values()]
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad

    out = {}
    for z in cfg['zooms']:
        span = TILE_PX // (2 ** z)
        out[z] = {
            'span': span,
            'tx': [x0 // span, x1 // span],
            'ty': [y0 // span, y1 // span],
        }
    coarse = out[min(cfg['zooms'])]
    span = coarse['span']
    return {
        'zooms': out,
        # top-left of the drawing area in game coordinates; y grows north in game
        # space but downward on screen, so the origin takes the *max* y.
        'origin': [coarse['tx'][0] * span, (coarse['ty'][1] + 1) * span],
        'size': [(coarse['tx'][1] - coarse['tx'][0] + 1) * span,
                 (coarse['ty'][1] - coarse['ty'][0] + 1) * span],
    }


def tile_url(cfg, z, x, y):
    return (cfg['tile_url']
            .replace('{version}', cfg['tile_version'])
            .replace('{map_id}', str(cfg['map_id']))
            .replace('{zoom}', str(z))
            .replace('{plane}', str(cfg['plane']))
            .replace('{x}', str(x))
            .replace('{y}', str(y)))


def tile_path(z, x, y):
    return f'{TILE_DIR}/{z}/{x}_{y}.png'
