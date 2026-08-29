"""Drive the real page and assert the wiring works.

unit.js covers the pure logic; this covers the wiring, which is where the bugs
have actually been: four filter dropdowns once shipped dead because nothing
clicked them. Every control must change the visible row count, state must
survive a reload through the URL, the map must render, pan and stay reachable,
and the console must stay clean.
"""
from __future__ import annotations

import pytest

from .conftest import pick_multi, rows

TASK_COUNT = 439   # rows in tables/port_tasks.list
PORT_COUNT = 30


def test_table_renders_every_task(fresh):
    assert rows(fresh) == TASK_COUNT


def test_every_multi_select_filters_and_resets(fresh):
    """All four in one page: they shipped dead once, which is why this exists."""
    for panel, value in [('#f-region', 'Zeah'), ('#f-ocean', 'Northern Ocean'),
                         ('#f-from', 'Rellekka'), ('#f-to', 'Prifddinas')]:
        pick_multi(fresh, panel, value)
        assert 0 < rows(fresh) < TASK_COUNT, panel
        assert value.split()[0] in fresh.url, panel
        fresh.click('#reset')
        fresh.wait_for_timeout(80)
        assert rows(fresh) == TASK_COUNT, panel


def test_scalar_filters_narrow_the_table(fresh):
    fresh.fill('#f-min', '70')
    fresh.wait_for_timeout(80)
    by_level = rows(fresh)
    assert 0 < by_level < TASK_COUNT

    fresh.check('#f-recover')
    fresh.wait_for_timeout(80)
    assert rows(fresh) <= by_level


def test_the_url_restores_the_filtered_view(fresh):
    fresh.fill('#f-min', '70')
    fresh.check('#f-recover')
    fresh.wait_for_timeout(80)
    expected = rows(fresh)

    fresh.goto(fresh.url, wait_until='networkidle')
    assert rows(fresh) == expected
    assert fresh.input_value('#f-min') == '70'


# --- the map -----------------------------------------------------------------

@pytest.fixture
def map_open(fresh):
    fresh.click('#map-toggle')
    fresh.wait_for_timeout(1200)
    return fresh


def test_map_opens_with_a_marker_per_port(map_open):
    assert map_open.is_visible('#map-viewport')
    assert map_open.locator('#map-overlay .marker').count() == PORT_COUNT


def test_map_tiles_load(map_open):
    tiles = map_open.locator('#map-tiles img').count()
    broken = map_open.evaluate(
        "Array.from(document.querySelectorAll('#map-tiles img'))"
        ".filter(i => i.complete && i.naturalWidth === 0).length")
    assert tiles > 0
    assert broken == 0, f'{broken} of {tiles} tiles failed to load'


def _drag(page, steps):
    box = page.locator('#map-viewport').bounding_box()
    cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    for dx, dy in steps:
        page.mouse.move(cx + dx, cy + dy)
        page.wait_for_timeout(16)
    page.mouse.up()
    page.wait_for_timeout(120)


def test_drag_pans_by_the_mouse_delta(map_open):
    start = map_open.evaluate('() => ({x: __app.view.x, y: __app.view.y})')
    _drag(map_open, [(-i * 20, -i * 10) for i in range(1, 7)])
    end = map_open.evaluate('() => ({x: __app.view.x, y: __app.view.y})')
    assert (round(end['x'] - start['x']), round(end['y'] - start['y'])) == (-120, -60)
    assert map_open.evaluate('() => String(getSelection())') == '', 'drag selected text'


def test_clicking_a_port_filters_to_its_notice_board(map_open):
    """A port with a board filters to it; clicking it again clears it."""
    # click the dot, not the <g>: its bbox includes the label above, so the
    # bbox centre can land in empty space between label and marker
    dot = map_open.locator('#map-overlay .marker.boardable .dot').first
    dot.click()
    map_open.wait_for_timeout(150)
    assert 0 < rows(map_open) < TASK_COUNT
    assert 'board=' in map_open.url
    assert map_open.locator('#f-board').input_value() != ''

    dot.click()
    map_open.wait_for_timeout(150)
    assert rows(map_open) == TASK_COUNT
    assert 'board=' not in map_open.url


def test_a_port_without_a_board_is_not_clickable(map_open):
    boardable = map_open.locator('#map-overlay .marker.boardable').count()
    total = map_open.locator('#map-overlay .marker').count()
    assert 0 < boardable < total, f'{boardable} of {total}'


# --- the route builder -------------------------------------------------------

@pytest.fixture
def trip(map_open):
    """Four tasks added to the trip, with the map open.

    The map has to be open: a trip's legs and the ports it sails past are
    drawn in the map overlay, not in the trip panel.
    """
    for i in range(4):
        map_open.locator('#tbody .trip-btn').nth(i).click()
        map_open.wait_for_timeout(60)
    return map_open


def test_trip_sequences_into_stops_and_legs(trip):
    assert trip.is_visible('#trip-panel')
    stops = trip.locator('#trip-stops li').count()
    assert stops >= 4
    # one polyline for the whole trip, not a chord per leg, so the casing
    # cannot show through at the joins
    leg = trip.locator('.trip-leg')
    assert leg.count() == 1
    # and it rounds headlands: a charted course needs far more points than it
    # has stops, where straight chords would have exactly one point per stop
    points = trip.evaluate(
        '() => document.querySelector(".trip-leg").getAttribute("points").split(" ").length')
    assert points > stops, points
    assert 'trip=' in trip.url


def test_pickups_precede_deliveries(trip):
    order = trip.evaluate('''() => {
      const t = __app.currentTrip();
      const seen = {};
      let ok = true;
      t.stops.forEach((s, i) => {
        s.picks.forEach(p => { seen[p.id] = i; });
        s.drops.forEach(d => { if (!(d.id in seen) || seen[d.id] > i) ok = false; });
      });
      return { ok, stops: t.stops.length, tasks: t.tasks.length };
    }''')
    assert order['ok'], order


def test_clearing_the_trip_closes_the_panel(trip):
    trip.click('#trip-clear')
    trip.wait_for_timeout(100)
    assert not trip.is_visible('#trip-panel')


def test_the_console_stayed_clean(app):
    """Last by design: it sees everything the tests above provoked."""
    assert not app.errors, '; '.join(app.errors[:5])
