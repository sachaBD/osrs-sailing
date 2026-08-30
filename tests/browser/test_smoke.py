"""Drive the real page and assert the wiring works.

unit.js covers the pure logic; this covers the wiring, which is where the bugs
have actually been: four filter dropdowns once shipped dead because nothing
clicked them. Every control must change the visible row count, state must
survive a reload through the URL, the map must render, pan and stay reachable,
and the console must stay clean.
"""
from __future__ import annotations

import pytest

from porttasks.paths import WEB

from .conftest import VIEWPORT, pick_multi, rows, wait_for_fewer_rows, wait_for_rows

TASK_COUNT = 439   # rows in tables/port_tasks.list
PORT_COUNT = 30


def test_table_renders_every_task(fresh):
    assert rows(fresh) == TASK_COUNT


def test_every_multi_select_filters_and_resets(fresh):
    """All five in one page: they shipped dead once, which is why this exists."""
    for panel, value in [('#f-region', 'Zeah'), ('#f-ocean', 'Northern Ocean'),
                         ('#f-from', 'Rellekka'), ('#f-to', 'Prifddinas'),
                         ('#f-calls', 'Port Sarim')]:
        pick_multi(fresh, panel, value)
        assert 0 < wait_for_fewer_rows(fresh, TASK_COUNT), panel
        assert value.split()[0] in fresh.url, panel
        fresh.click('#reset')
        wait_for_rows(fresh, TASK_COUNT)


def test_scalar_filters_narrow_the_table(fresh):
    fresh.fill('#f-min', '70')
    by_level = wait_for_fewer_rows(fresh, TASK_COUNT)
    assert by_level > 0

    fresh.check('#f-recover')
    fresh.wait_for_function('n => document.querySelectorAll("#tbody tr").length <= n',
                            arg=by_level)


def test_the_url_restores_the_filtered_view(fresh):
    fresh.fill('#f-min', '70')
    fresh.check('#f-recover')
    expected = wait_for_fewer_rows(fresh, TASK_COUNT)

    fresh.goto(fresh.url, wait_until='networkidle')
    assert rows(fresh) == expected
    assert fresh.input_value('#f-min') == '70'


# --- the map -----------------------------------------------------------------

@pytest.fixture
def map_open(fresh):
    fresh.click('#map-toggle')
    # the overlay is drawn on the first reveal, so a marker means the viewer
    # has sized itself, fitted the ports and handed the SVG over
    fresh.wait_for_selector('#map-overlay .marker')
    return fresh


def test_map_opens_with_a_marker_per_port(map_open):
    assert map_open.is_visible('#map-viewport')
    assert map_open.locator('#map-overlay .marker').count() == PORT_COUNT


@pytest.mark.skipif(not any((WEB / 'tiles').glob('**/*.png')),
                    reason='no web/tiles; run `make tiles` to check the real ones')
def test_map_tiles_load(browser, app_url):
    """The tile grid and URL template, against the tiles on disk.

    The only test that loads real tiles, so the only one that needs them there.
    """
    page = browser.new_page(viewport=VIEWPORT)
    try:
        page.goto(app_url + '/?map=1', wait_until='networkidle')
        tiles = page.locator('#map-tiles img').count()
        broken = page.evaluate(
            "Array.from(document.querySelectorAll('#map-tiles img'))"
            ".filter(i => i.complete && i.naturalWidth === 0).length")
        assert tiles > 0
        assert broken == 0, f'{broken} of {tiles} tiles failed to load'
    finally:
        page.close()


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
    assert 0 < wait_for_fewer_rows(map_open, TASK_COUNT)
    assert 'board=' in map_open.url
    assert map_open.locator('#f-board').input_value() != ''

    dot.click()
    wait_for_rows(map_open, TASK_COUNT)
    assert 'board=' not in map_open.url

    # and the ports without a board are not offered as clickable at all
    boardable = map_open.locator('#map-overlay .marker.boardable').count()
    total = map_open.locator('#map-overlay .marker').count()
    assert 0 < boardable < total, f'{boardable} of {total}'


# --- the route builder -------------------------------------------------------

# the four highest-XP tasks, which is what the table's default sort puts on top
TRIP = '1~2~3~4'


@pytest.fixture
def trip(fresh):
    """Four tasks in the trip, with the map open.

    Built through the URL rather than by clicking, because ten tests want a
    trip and none of them is about how one is assembled - the + button has
    `test_the_button_adds_a_task_to_the_trip` to itself. The map has to be
    open: a trip's legs and the ports it sails past are drawn in the overlay,
    not in the trip panel.
    """
    fresh.goto(f'{fresh.base_url}?map=1&trip={TRIP}', wait_until='commit')
    fresh.wait_for_selector('#map-overlay .marker')
    fresh.wait_for_selector('#trip-panel:not([hidden])')
    return fresh


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


def test_the_button_adds_a_task_to_the_trip(fresh):
    """How a trip gets built. Every other trip test loads one from the URL."""
    assert not fresh.is_visible('#trip-panel')
    fresh.locator('#tbody .trip-btn').first.click()
    fresh.wait_for_selector('#trip-panel:not([hidden])')
    assert 'trip=' in fresh.url
    assert fresh.locator('#trip-stops li').count() == 2   # a pickup and a delivery

    fresh.locator('#tbody .trip-btn').first.click()       # and it toggles back off
    # `hidden` is never "visible", so wait on the attribute rather than on sight
    fresh.wait_for_selector('#trip-panel[hidden]', state='attached')


def _passing_ports(page) -> list[str]:
    return page.eval_on_selector_all('#trip-passing .pass', 'els => els.map(e => e.dataset.port)')


def test_a_passing_port_filters_to_tasks_at_either_end(trip):
    """The chips answer "is there work at this port", not "what does its board
    offer": a port you sail past is worth a call if a task loads or delivers
    there, whoever posted it."""
    trip.fill('#trip-corridor', '400')     # wide enough to be sure of a chip
    ports = _passing_ports(trip)
    assert ports, 'no ports listed as passed'

    trip.locator('#trip-passing .pass').first.click()
    port = ports[0]
    wait_for_fewer_rows(trip, TASK_COUNT)
    assert 'calls=' in trip.url
    assert 'board=' not in trip.url
    assert 0 < rows(trip) < TASK_COUNT
    ends = trip.eval_on_selector_all(
        '#tbody tr', 'rows => rows.map(r => [r.children[4].textContent,'
                     ' r.children[5].textContent])')
    assert all(port in row for row in ends), (port, ends[:3])

    trip.locator('#trip-passing .pass').first.click()   # clicking again clears it
    wait_for_rows(trip, TASK_COUNT)
    assert 'calls=' not in trip.url


def test_every_passing_port_is_clickable(trip):
    """Clickability marks a port, not a notice board: the tick marks the board.

    Cargo runs to and from ports with no board of their own, so the filter is
    worth offering on those chips too.
    """
    trip.fill('#trip-corridor', '400')
    chips = trip.locator('#trip-passing .pass').count()
    assert chips > 0
    assert trip.locator('#trip-passing button.pass[data-port]').count() == chips


def _lifts(page) -> list[float | None]:
    """The Delta XP/hr column, as numbers; None for the em dash."""
    cells = page.eval_on_selector_all(
        '#tbody tr td:last-child', 'cs => cs.map(c => c.textContent.trim())')
    return [None if c == '\u2014'
            else float(c.replace(',', '').replace('\u2212', '-').lstrip('+'))
            for c in cells]


def test_nothing_is_priced_against_a_trip_that_does_not_exist(fresh):
    """Both of the trip-relative measures go quiet together: there is no rate
    to price against, and XP/hr already answers the standalone case."""
    assert set(_lifts(fresh)) == {None}
    assert not fresh.is_visible('#boards-panel')


def test_the_lift_ranks_what_to_add_to_the_trip(trip):
    trip.click('th[data-key="lift"]')          # sorts descending by default
    values = _lifts(trip)
    known = [v for v in values if v is not None]

    assert len(known) > len(values) / 2, 'almost every task should price'
    assert known == sorted(known, reverse=True)
    assert values[:len(known)] == known, 'unpriced tasks must sink to the bottom'
    assert known[0] > 0, 'some task must be worth adding'
    assert any(v < 0 for v in known), 'and some must not be'


def test_the_lift_moves_when_the_trip_does(trip):
    """It is a lift against this trip, not a property of the task."""
    before = _lifts(trip)
    trip.locator('#tbody .trip-btn').nth(8).click()   # one more task in the trip
    assert _lifts(trip) != before


def _boards(page) -> list[list[str]]:
    return page.eval_on_selector_all(
        '#boards-rows tr', 'rs => rs.map(r => [...r.children].map(c => c.textContent.trim()))')


def _value(cell: str) -> float:
    return float(cell.replace(',', ''))


def test_boards_rank_by_what_a_stop_is_worth(trip):
    rows = _boards(trip)
    assert rows, 'no board is worth a stop against this trip'
    values = [_value(r[2]) for r in rows]
    assert values == sorted(values, reverse=True)
    assert all(v > 0 for v in values), 'worthless boards belong in the tail count'
    # the luckiest draw is an upper bound on the average one
    assert all(_value(r[4]) >= _value(r[2]) for r in rows)


def test_more_room_in_the_hold_never_lowers_a_board(trip):
    one = {r[0]: _value(r[2]) for r in _boards(trip)}
    trip.fill('#board-slots', '3')
    three = {r[0]: _value(r[2]) for r in _boards(trip)}
    assert three, 'the panel emptied when the hold grew'
    assert all(v >= one.get(port, 0) for port, v in three.items())
    assert 'freeSlots=3' in trip.url


def test_the_map_shows_what_each_board_is_worth(trip):
    """The halo is the map's half of the same number the panel ranks."""
    haloed = trip.eval_on_selector_all(
        '#map-overlay .marker.worth-a-stop .worth', 'cs => cs.map(c => +c.getAttribute("r"))')
    assert len(haloed) == len(_boards(trip))
    # area carries the value, so the best board draws the largest disc
    assert max(haloed) > min(haloed)

    trip.click('#trip-clear')
    assert trip.locator('#map-overlay .marker .worth').count() == 0


def test_clearing_the_trip_closes_the_panel(trip):
    trip.click('#trip-clear')
    assert not trip.is_visible('#trip-panel')


# --- on a phone ---------------------------------------------------------------

# Two fingers, dispatched as the pointer events a touch screen would raise.
# Playwright drives one touch point at a time, so a real pinch has to be
# synthesised; what it exercises is the viewer's own handler, which is the part
# that can break.
PINCH = """([spread, steps]) => {
  const vp = document.querySelector('#map-viewport');
  const box = vp.getBoundingClientRect();
  const send = (type, id, x, y) => vp.dispatchEvent(new PointerEvent(type, {
    pointerId: id, pointerType: 'touch', isPrimary: id === 1,
    clientX: x, clientY: y, bubbles: true, cancelable: true }));
  const [cx, cy] = [box.left + box.width / 2, box.top + box.height / 2];
  const reach = 60;
  send('pointerdown', 1, cx - reach, cy);
  send('pointerdown', 2, cx + reach, cy);
  for (let i = 1; i <= steps; i++) {
    const r = reach * (1 + (spread - 1) * (i / steps));
    send('pointermove', 1, cx - r, cy);
    send('pointermove', 2, cx + r, cy);
  }
  send('pointerup', 1, cx, cy);
  send('pointerup', 2, cx, cy);
  return __app.view.scale;
}"""


def test_the_page_fits_a_phone(phone):
    """Nothing may push the body sideways: a horizontally scrolling page makes
    every vertical swipe a fight."""
    width, viewport = phone.evaluate(
        '() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]')
    assert width <= viewport, f'{width}px of content in a {viewport}px viewport'
    # the results table is the one thing too wide to fit, so it scrolls itself
    assert phone.evaluate("() => { const w = document.querySelector('.table-wrap');"
                          ' return w.scrollWidth > w.clientWidth; }')


def test_two_fingers_zoom_the_map(phone):
    before = phone.evaluate('() => __app.view.scale')
    apart = phone.evaluate(PINCH, [2.0, 8])
    assert apart > before * 1.3, f'{before} -> {apart}'
    together = phone.evaluate(PINCH, [0.5, 8])
    assert together < apart * 0.8, f'{apart} -> {together}'


def test_a_phone_starts_with_the_filters_folded(phone):
    """Fourteen filter fields are a screenful before the map or the table."""
    assert not phone.is_visible('#f-q')
    assert phone.is_visible('#map-viewport')

    phone.click('#filters-toggle')
    assert phone.is_visible('#f-q')


def test_a_folded_bar_still_says_it_is_filtering(phone):
    phone.click('#filters-toggle')
    phone.fill('#f-min', '70')
    phone.click('#filters-toggle')
    assert not phone.is_visible('#f-q')
    assert 'of' in phone.text_content('#filters-toggle')


def test_tap_targets_are_big_enough_to_hit(phone):
    """iOS zooms the page when a control under 16px takes focus, which throws
    away the viewport the map is sized against."""
    phone.click('#filters-toggle')
    fonts = phone.eval_on_selector_all(
        '.filters input, .filters select',
        'els => els.map(e => parseFloat(getComputedStyle(e).fontSize))')
    assert fonts and min(fonts) >= 16, fonts
    # and a fingertip has to be able to land on a port
    hit = phone.eval_on_selector('#map-overlay .marker .hit',
                                 'c => parseFloat(getComputedStyle(c).r)')
    assert hit >= 20, hit


def test_the_console_stayed_clean(app):
    """Last by design: it sees everything the tests above provoked."""
    assert not app.errors, '; '.join(app.errors[:5])
