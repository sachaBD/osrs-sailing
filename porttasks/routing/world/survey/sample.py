"""A contact sheet of sampled routes, one per panel, for checking by eye.

    python3 -m porttasks.routing.world.survey.sample            25 routes, seed 0
    python3 -m porttasks.routing.world.survey.sample 12 7       12 routes, seed 7

Twenty-five routes drawn on one map is a ball of wool.  One route per panel,
each cropped to the water it uses, is checkable: the question for each is only
"would a ship go that way", and the distance is printed beside it.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from porttasks.paths import RENDERS

from ..catalogue import Catalogue
from ..distances import Distances
from . import measure, watermask
from .render import _FONT, _basemap

OUT = RENDERS / 'routes_sample.png'
PANEL = 460        # side of one panel, in pixels
CAPTION = 34       # caption strip below each panel
MARGIN = 0.18      # of the route's bounding box, added as breathing room
MIN_SPAN = 190     # smallest crop, in game tiles, so short hops are not over-zoomed
COLUMNS = 5

ROUTE = (255, 92, 92)
ENDS = (255, 232, 130)


def _crop_box(track: list[tuple[int, int]], size: int) -> tuple[int, int, int, int]:
    rows = [p[0] for p in track]
    cols = [p[1] for p in track]
    height, width = max(rows) - min(rows), max(cols) - min(cols)
    span = max(height, width, MIN_SPAN) * (1 + MARGIN)
    centre_row = (max(rows) + min(rows)) / 2
    centre_col = (max(cols) + min(cols)) / 2
    left = min(max(0, int(centre_col - span / 2)), size - int(span))
    top = min(max(0, int(centre_row - span / 2)), size - int(span))
    return left, top, left + int(span), top + int(span)


def panel(base: Image.Image, track: list[tuple[int, int]], caption: str,
          font: ImageFont.FreeTypeFont) -> Image.Image:
    box = _crop_box(track, base.width)
    scale = PANEL / (box[2] - box[0])

    view = base.crop(box).resize((PANEL, PANEL), Image.LANCZOS)
    draw = ImageDraw.Draw(view, 'RGBA')
    points = [((c - box[0]) * scale, (r - box[1]) * scale) for r, c in track]
    draw.line(points, fill=ROUTE, width=3, joint='curve')
    for x, y in (points[0], points[-1]):
        draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=ENDS, outline=(20, 20, 20))

    tile = Image.new('RGB', (PANEL, PANEL + CAPTION), (16, 18, 24))
    tile.paste(view, (0, 0))
    ImageDraw.Draw(tile).text((7, PANEL + 9), caption, font=font, fill=(236, 240, 248))
    return tile


def main(argv: list[str]) -> None:
    count = int(argv[0]) if argv else 25
    seed = int(argv[1]) if len(argv) > 1 else 0

    matrix = Distances.load()
    world = Catalogue.load()
    mask = watermask.build()
    with open(measure.ROUTES) as f:
        routes = json.load(f)

    pairs = [(a, b) for i, a in enumerate(matrix.ports) for b in matrix.ports[i + 1:]]
    chosen = random.Random(seed).sample(pairs, min(count, len(pairs)))
    chosen.sort(key=lambda p: matrix.between(*p))

    base = _basemap(mask, tiles=False)
    font = ImageFont.truetype(_FONT, 16)
    tiles = [panel(base, [tuple(p) for p in routes[a][b]],
                   f'{a} - {b}   {matrix.between(a, b):.0f}', font)
             for a, b in chosen]

    columns = min(COLUMNS, len(tiles))
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new('RGB', (columns * (PANEL + 6) + 6, rows * (PANEL + CAPTION + 6) + 6),
                      (10, 11, 15))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (6 + (i % columns) * (PANEL + 6),
                           6 + (i // columns) * (PANEL + CAPTION + 6)))
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT)
    print(f'{OUT}: {len(tiles)} routes, seed {seed}')
    for a, b in chosen:
        straight = (sum((x - y) ** 2 for x, y in
                        zip(world.ports[a].coords, world.ports[b].coords))) ** 0.5
        print(f'  {a:22s} {b:22s} {matrix.between(a, b):6.0f} tiles   '
              f'x{matrix.between(a, b) / straight:.2f} straight')


if __name__ == '__main__':
    main(sys.argv[1:])
