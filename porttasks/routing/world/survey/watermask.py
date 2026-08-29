"""The ocean, as a boolean grid, read out of the cached map tiles.

The wiki's zoom-0 tiles are one pixel per game tile, so `make tiles` already
gives us a navigable raster.  Water is classified by colour: everything the
renderer draws as sea is blue-led, while land, roads and the unmapped void
are not.  The rule has to admit the shallows, which are teal rather than blue
and speckled with darker kelp, so it asks only that blue leads green rather
than beating it - and a closing pass then fills the kelp back in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from glob import glob

import numpy as np
from PIL import Image
from scipy import ndimage

from porttasks.routing.errors import SurveyError
from porttasks.tiles import grid

NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))


@dataclass(frozen=True)
class WaterMask:
    """Water/not-water in game coordinates, with the open sea marked out.

    Rows run north to south, so a game y maps to a row of `origin_y - 1 - y`.
    """
    water: np.ndarray
    sea: np.ndarray  # the largest connected body: ocean, not inland lakes
    origin: tuple[int, int]  # game (x, y) of pixel (0, 0)

    @property
    def shape(self) -> tuple[int, int]:
        return self.water.shape  # type: ignore[return-value]

    def to_rc(self, x: float, y: float) -> tuple[int, int]:
        return int(self.origin[1] - 1 - y), int(x - self.origin[0])

    def to_xy(self, row: int, col: int) -> tuple[int, int]:
        return self.origin[0] + col, self.origin[1] - 1 - row

    def sea_at(self, row: int, col: int) -> bool:
        height, width = self.shape
        return 0 <= row < height and 0 <= col < width and bool(self.sea[row, col])


def _mosaic(tile_dir: str, zoom: int) -> tuple[np.ndarray, tuple[int, int]]:
    bounds = grid.bounds()['zooms'][zoom]
    span, (tx0, tx1), (ty0, ty1) = bounds['span'], bounds['tx'], bounds['ty']
    image = np.zeros(((ty1 - ty0 + 1) * span, (tx1 - tx0 + 1) * span, 3), np.uint8)

    paths = glob(f'{tile_dir}/{zoom}/*.png')
    if not paths:
        raise SurveyError(f'no tiles in {tile_dir}/{zoom}; run `make tiles`')
    for path in paths:
        match = re.search(r'(\d+)_(\d+)\.png$', path)
        if not match:
            continue
        tx, ty = int(match.group(1)), int(match.group(2))
        if not (tx0 <= tx <= tx1 and ty0 <= ty <= ty1):
            continue
        # game y grows north but image rows grow south, so the top tile row is ty1
        row, col = (ty1 - ty) * span, (tx - tx0) * span
        image[row:row + span, col:col + span] = np.asarray(Image.open(path).convert('RGB'))
    return image, (tx0 * span, (ty1 + 1) * span)


KELP = 5  # closing window, in game tiles: kelp specks are a few tiles across
TINT = 8  # how far blue must lead red before a grey counts as water


def _largest_body(water: np.ndarray) -> np.ndarray:
    """Keep only the biggest connected body of water: the ocean, not the lakes."""
    label, _ = ndimage.label(water, np.ones((3, 3)))
    sizes = np.bincount(label.ravel())
    sizes[0] = 0
    return label == sizes.argmax()


def build(tile_dir=grid.TILE_ROOT, zoom: int = 0) -> WaterMask:
    image, origin = _mosaic(tile_dir, zoom)
    red, green, blue = (image[:, :, i].astype(np.int16) for i in range(3))
    blue_led = (blue >= green) & (green >= red) & (blue - red >= TINT)
    water = ndimage.binary_closing(blue_led, np.ones((KELP, KELP)))
    return WaterMask(water=water, sea=_largest_body(water), origin=origin)
