"""Draw the sea graph over the world map, so its shortcuts can be eyeballed.

    python3 -m porttasks.routing.world.survey.render                     the graph alone
    python3 -m porttasks.routing.world.survey.render --tiles             over the real map tiles
    python3 -m porttasks.routing.world.survey.render Catherby Aldarin    plus that route
    python3 -m porttasks.routing.world.survey.render --lanes             every pair's exact route

What to look for: legs that cut across a headland or an isthmus, ports whose
approach leaves the harbour the wrong way, stretches of open water with no
waypoints to plan through, and - with --tiles - coastline the colour rule got
wrong in either direction.
"""
from __future__ import annotations

import heapq
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from porttasks.paths import PORT_ROUTES as ROUTES_FILE
from porttasks.paths import RENDERS
from porttasks.routing.errors import SurveyError

from . import watermask
from .seagraph import SeaGraph

OUT = RENDERS / 'graph.png'
_FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

SEA = (12, 26, 48)
SHALLOW = (26, 48, 74)
LAND = (92, 88, 72)
COAST = (150, 200, 235)
LEG = (70, 118, 165)
WAYPOINT = (130, 190, 235)
APPROACH = (245, 170, 60)
PORT = (255, 232, 130)
ROUTE = (255, 70, 70)
LANE = (120, 255, 190)


def shortest_path(graph: SeaGraph, origin: str, destination: str) -> tuple[list[int], float]:
    """Cheapest sequence of waypoints from one berth to another."""
    for name in (origin, destination):
        if name not in graph.berths:
            raise SurveyError(f'unknown port {name!r}')
    start, goal = graph.berths[origin], graph.berths[destination]
    dist = {start: 0.0}
    prev: dict[int, int] = {}
    queue = [(0.0, start)]
    while queue:
        cost, node = heapq.heappop(queue)
        if node == goal:
            break
        if cost > dist.get(node, float('inf')):
            continue
        for other, length in graph.edges.get(node, {}).items():
            step = cost + length
            if step < dist.get(other, float('inf')):
                dist[other] = step
                prev[other] = node
                heapq.heappush(queue, (step, other))
    if goal not in dist:
        raise SurveyError(f'no charted route {origin} -> {destination}')

    path, node = [goal], goal
    while node != start:
        node = prev[node]
        path.append(node)
    return path[::-1], dist[goal]


def _basemap(mask: watermask.WaterMask, tiles: bool) -> Image.Image:
    """Either the rendered tiles, dimmed, or a flat map of the mask itself.

    The flat version shows exactly what the router believes; the dimmed tiles
    show what is actually there.  Disagreements between them are the bugs.
    """
    if tiles:
        image, _ = watermask._mosaic('tiles', 0)
        return Image.fromarray((image * 0.45).astype(np.uint8))

    height, width = mask.shape
    canvas = np.zeros((height, width, 3), np.uint8)
    canvas[:] = LAND
    canvas[mask.water] = SHALLOW
    canvas[mask.sea] = SEA
    # a one-pixel coastline, so the shapes read at a glance
    edge = mask.sea & ~ndimage.binary_erosion(mask.sea, np.ones((3, 3)))
    canvas[edge] = COAST
    return Image.fromarray(canvas)


def _label(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, name: str,
           row: int, col: int, width: int) -> None:
    """Put the name beside the marker, flipping to its left near the edge."""
    text_width = draw.textlength(name, font=font)
    x = col + 9 if col + 9 + text_width < width - 4 else col - 9 - text_width
    box = draw.textbbox((x, row - 8), name, font=font)
    draw.rectangle([box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2], fill=(0, 0, 0, 170))
    draw.text((x, row - 8), name, font=font, fill=(255, 255, 255))


def _lanes(draw: ImageDraw.ImageDraw) -> None:
    """Every port pair's pixel-exact route, stacked up into the sea lanes.

    Where many routes share water the colour saturates, which is what a busy
    channel looks like - and an empty ocean with routes skirting it is the
    clearest sign the mask has invented a barrier.
    """
    with open(ROUTES_FILE) as f:
        routes = json.load(f)
    for origin, row in routes.items():
        for destination, track in row.items():
            if origin < destination:
                draw.line([(c, r) for r, c in track], fill=(*LANE, 26), width=2)


def render(graph: SeaGraph, mask: watermask.WaterMask, route: list[str] | None = None,
           tiles: bool = False, lanes: bool = False, path: str = OUT) -> str:
    image = _basemap(mask, tiles)
    draw = ImageDraw.Draw(image, 'RGBA')
    berths = set(graph.berths.values())
    node = graph.nodes

    if lanes:
        _lanes(draw)

    if not lanes:
        for i, links in graph.edges.items():
            for j in links:
                if j < i or i in berths or j in berths:
                    continue
                draw.line([node[i][1], node[i][0], node[j][1], node[j][0]],
                          fill=(*LEG, 130), width=1)

        # approaches are sailed round the harbour mouth: draw the track, not a chord
        for berth, links in graph.approaches.items():
            for track in links.values():
                draw.line([(c, r) for r, c in track], fill=(*APPROACH, 220), width=2)
    for i in graph.edges:
        if i not in berths:
            row, col = node[i]
            draw.point([(col, row)], fill=WAYPOINT)

    for origin, destination in zip(route or [], (route or [])[1:]):
        legs, length = shortest_path(graph, origin, destination)
        draw.line([(node[i][1], node[i][0]) for i in legs], fill=ROUTE, width=3, joint='curve')
        print(f'  {origin} -> {destination}: {length:.0f} tiles')

    font = ImageFont.truetype(_FONT, 15)
    for name, berth in sorted(graph.berths.items()):
        row, col = node[berth]
        draw.ellipse([col - 5, row - 5, col + 5, row + 5], fill=PORT, outline=(20, 20, 20))
        _label(draw, font, name, row, col, image.width)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def main(argv: list[str]) -> None:
    tiles = '--tiles' in argv
    lanes = '--lanes' in argv
    route = [a for a in argv if not a.startswith('--')]
    graph = SeaGraph.load()
    mask = watermask.build()
    if route:
        print('route:')
    suffix = ('_lanes' if lanes else '') + ('_tiles' if tiles else '')
    out = render(graph, mask, route or None, tiles, lanes,
                 OUT.replace('.png', f'{suffix}.png') if suffix else OUT)
    size = Path(out).stat().st_size / 1e6
    print(f'{out}: {len(graph.edges)} waypoints, {graph.leg_count} legs, '
          f'{len(graph.berths)} ports ({size:.1f}MB)')


if __name__ == '__main__':
    main(sys.argv[1:])
