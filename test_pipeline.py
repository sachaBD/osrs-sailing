"""Unit tests for the data pipeline. Run with `make check` or `python3 -m unittest`."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import build
import locations
import mapdata
import parse_list


class ParseList(unittest.TestCase):
    def setUp(self) -> None:
        self.tasks = parse_list.parse()

    def test_every_row_is_read(self) -> None:
        raw = Path(parse_list.SRC).read_text().splitlines()
        # 3 header lines, and trailing blanks the parser skips
        expected = len([l for l in raw[3:] if l.count('\t') == 8])
        self.assertEqual(len(self.tasks), expected)

    def test_ids_are_unique(self) -> None:
        ids = [t['id'] for t in self.tasks]
        self.assertEqual(len(ids), len(set(ids)))

    def test_unknown_xp_becomes_none(self) -> None:
        unknown = [t for t in self.tasks if t['xp'] is None]
        self.assertTrue(unknown, 'expected some Unknown-XP rows')
        self.assertTrue(all(t['qty'] > 0 for t in unknown))

    def test_board_is_always_one_end(self) -> None:
        for t in self.tasks:
            self.assertIn(t['noticeBoard'], (t['from'], t['to']), t)

    def test_direction_matches_the_board(self) -> None:
        for t in self.tasks:
            expected = 'outbound' if t['noticeBoard'] == t['from'] else 'inbound'
            self.assertEqual(t['direction'], expected, t)


class Locations(unittest.TestCase):
    def setUp(self) -> None:
        self.ports = locations.load()

    def test_every_task_port_is_described(self) -> None:
        used = {t[k] for t in parse_list.parse() for k in ('noticeBoard', 'from', 'to')}
        self.assertEqual(used - set(self.ports), set())

    def test_every_port_has_coordinates(self) -> None:
        missing = [n for n, p in self.ports.items() if not p['coords']]
        self.assertEqual(missing, [])

    def test_oceans_are_a_list(self) -> None:
        self.assertEqual(self.ports['Corsair Cove']['oceans'],
                         ['Ardent Ocean', 'Shrouded Ocean'])

    def test_round_trip_preserves_everything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'locations.tsv')
            Path(path).write_text(Path(locations.PATH).read_text())
            locations.save(self.ports, path)
            self.assertEqual(locations.load(path), self.ports)

    def test_bad_header_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.tsv'
            path.write_text('# note\nname\tregion\nAldarin\tZeah\n')
            with self.assertRaises(locations.LocationsError):
                locations.load(str(path))


class MapGrid(unittest.TestCase):
    def test_bounds_cover_every_port(self) -> None:
        cfg = mapdata.config()
        coords = mapdata.port_coords()
        bounds = mapdata.bounds(cfg, coords)
        for zoom, grid in bounds['zooms'].items():
            span = grid['span']
            for name, (x, y) in coords.items():
                self.assertTrue(grid['tx'][0] <= x // span <= grid['tx'][1], f'{name} x at z{zoom}')
                self.assertTrue(grid['ty'][0] <= y // span <= grid['ty'][1], f'{name} y at z{zoom}')

    def test_zoom_levels_nest(self) -> None:
        bounds = mapdata.bounds()
        spans = [g['span'] for g in bounds['zooms'].values()]
        for finer in spans[1:]:
            self.assertEqual(spans[0] % finer, 0, 'finer tiles must divide the coarsest')

    def test_tile_url_substitutes_everything(self) -> None:
        url = mapdata.tile_url(mapdata.config(), 0, 5, 9)
        self.assertNotIn('{', url)
        self.assertTrue(url.startswith('https://'))


class Build(unittest.TestCase):
    def test_map_info_is_json_serialisable(self) -> None:
        json.dumps(build.map_info())


if __name__ == '__main__':
    unittest.main()
