"""The data pipeline: parsing the tables, and the tile grid built from them."""
from __future__ import annotations

from pathlib import Path

import pytest

from porttasks.tables import locations, tasks
from porttasks.tiles import grid


@pytest.fixture(scope='module')
def rows() -> list[dict]:
    return tasks.parse()


@pytest.fixture(scope='module')
def ports() -> dict:
    return locations.load()


# --- port_tasks.list ---------------------------------------------------------

def test_every_row_is_read(rows):
    raw = Path(tasks.SRC).read_text().splitlines()
    # 3 header lines, and trailing blanks the parser skips
    expected = len([line for line in raw[3:] if line.count('\t') == 8])
    assert len(rows) == expected


def test_unknown_xp_becomes_none(rows):
    unknown = [t for t in rows if t['xp'] is None]
    assert unknown, 'expected some Unknown-XP rows'
    assert all(t['qty'] > 0 for t in unknown)


def test_the_board_is_always_one_end_of_the_task(rows):
    assert [t for t in rows if t['noticeBoard'] not in (t['from'], t['to'])] == []


# --- locations.tsv -----------------------------------------------------------

def test_every_task_port_is_described(rows, ports):
    used = {t[k] for t in rows for k in ('noticeBoard', 'from', 'to')}
    assert used - set(ports) == set()


def test_every_port_has_coordinates(ports):
    assert [name for name, p in ports.items() if not p['coords']] == []


def test_round_trip_preserves_everything(ports, tmp_path):
    path = tmp_path / 'locations.tsv'
    path.write_text(Path(locations.PATH).read_text())
    locations.save(ports, str(path))
    assert locations.load(str(path)) == ports


def test_a_bad_header_is_rejected(tmp_path):
    path = tmp_path / 'bad.tsv'
    path.write_text('# note\nname\tregion\nAldarin\tZeah\n')
    with pytest.raises(locations.LocationsError):
        locations.load(str(path))


# --- the tile grid -----------------------------------------------------------

def test_bounds_cover_every_port():
    cfg = grid.config()
    coords = grid.port_coords()
    bounds = grid.bounds(cfg, coords)
    for zoom, level in bounds['zooms'].items():
        span = level['span']
        for name, (x, y) in coords.items():
            assert level['tx'][0] <= x // span <= level['tx'][1], f'{name} x at z{zoom}'
            assert level['ty'][0] <= y // span <= level['ty'][1], f'{name} y at z{zoom}'


def test_tile_url_substitutes_everything():
    url = grid.tile_url(grid.config(), 0, 5, 9)
    assert '{' not in url
    assert url.startswith('https://')
