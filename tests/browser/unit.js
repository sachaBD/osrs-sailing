/* Unit tests for the pure logic, run inside a real browser by test_unit_js.py.
   Anything needing the DOM or the map belongs in test_smoke.py instead. */
import { esc } from '../../web/js/dom.js';
import {
  TASKS, TASK_BY_ID, allPorts, allRegions, allOceans,
  regionOf, oceansOf, canRecoverAt, hasBoardAt, portXY, legsOf,
} from '../../web/js/ports.js';
import { state } from '../../web/js/state.js';
import { filtered, sorted, matchesScope } from '../../web/js/filters.js';
import {
  sequenceTrip, portsNearRoute, distanceToSegment, priceTrip, xpLift,
} from '../../web/js/trip.js';
import { legDistance, routeSeconds } from '../../web/js/cost.js';

const results = [];
const check = (name, cond, detail = '') => results.push({ name, ok: !!cond, detail });
const near = (a, b, tol = 0.001) => Math.abs(a - b) < tol;

/* ---- dom ---- */
check('esc neutralises quotes', esc(`Land's "End" & <b>`) === 'Land&#39;s &quot;End&quot; &amp; &lt;b&gt;');

/* ---- geometry ---- */
check('point on segment has zero distance', near(distanceToSegment([5, 0], [0, 0], [10, 0]), 0));
check('perpendicular distance', near(distanceToSegment([5, 3], [0, 0], [10, 0]), 3));
check('past the end clamps to the endpoint',
  near(distanceToSegment([20, 0], [0, 0], [10, 0]), 10));
check('degenerate segment falls back to point distance',
  near(distanceToSegment([3, 4], [0, 0], [0, 0]), 5));

/* ---- ports ---- */
check('every port is mapped', allPorts.length === 30, `${allPorts.length}`);
check('every task id resolves', TASKS.every((t) => TASK_BY_ID.get(t.id) === t));
check('regions are known', allRegions.includes('Zeah') && !allRegions.includes('Unknown'));
check('oceans are known', allOceans.includes('Northern Ocean'), allOceans.join(','));
check('Zeah covers Kourend and Varlamore',
  regionOf('Port Piscarilius') === 'Zeah' && regionOf('Civitas illa Fortis') === 'Zeah');
check('Corsair Cove sits in two oceans', oceansOf('Corsair Cove').length === 2,
  oceansOf('Corsair Cove').join(','));
check('shipwright lookup', canRecoverAt('Port Sarim') === true && canRecoverAt('Entrana') === false);
check('notice board lookup', hasBoardAt('Port Sarim') === true && hasBoardAt('Entrana') === false);
check('every port has coordinates', allPorts.every((p) => portXY(p) !== null));
check('unknown port degrades quietly',
  portXY('Atlantis') === null && regionOf('Atlantis') === 'Unknown' && oceansOf('Atlantis').length === 0);
check('legsOf names the three ports', (() => {
  const t = TASKS[0];
  const l = legsOf(t);
  return l.board === t.noticeBoard && l.from === t.from && l.to === t.to;
})());

/* ---- filters ---- */
const withState = (patch, fn) => {
  const saved = {};
  for (const k of Object.keys(patch)) saved[k] = state[k];
  Object.assign(state, patch);
  try { return fn(); } finally { Object.assign(state, saved); }
};

check('unfiltered shows everything', filtered().length === TASKS.length);
check('level bounds apply',
  withState({ minLevel: 70 }, () => filtered().every((t) => t.level >= 70)));
check('xp bounds exclude unknown xp',
  withState({ minXp: 1 }, () => filtered().every((t) => t.xp !== null)));
check('scope=both needs each end in the region', withState(
  { region: new Set(['Zeah']), scope: 'both' },
  () => filtered().every((t) => regionOf(t.from) === 'Zeah' && regionOf(t.to) === 'Zeah')));
check('scope=any accepts one end', withState(
  { region: new Set(['Zeah']), scope: 'any' },
  () => filtered().length > withState(
    { region: new Set(['Zeah']), scope: 'both' }, () => filtered().length)));
check('matchesScope passes when nothing is selected',
  matchesScope(TASKS[0], new Set(), () => []));
check('calls takes a port at either end', withState(
  { calls: new Set(['Port Sarim']) },
  () => filtered().every((t) => t.from === 'Port Sarim' || t.to === 'Port Sarim')));
check('calls is not the notice board filter', withState(
  { calls: new Set(['Port Sarim']) },
  () => filtered().some((t) => t.noticeBoard !== 'Port Sarim')
    && filtered().some((t) => t.from === 'Port Sarim')
    && filtered().some((t) => t.to === 'Port Sarim')));
check('sorting nulls sink regardless of direction', (() => {
  const rows = TASKS.slice();
  const desc = withState({ sortKey: 'xp', sortDir: 'desc' }, () => sorted(rows));
  const asc = withState({ sortKey: 'xp', sortDir: 'asc' }, () => sorted(rows));
  return desc[desc.length - 1].xp === null && asc[asc.length - 1].xp === null;
})());

/* ---- URL parameter names are a public surface: links get shared ---- */
import { stateToUrl, urlToState } from '../../web/js/state.js';

check('url uses the published parameter names', withState(
  { mapOpen: true, showAllRoutes: true, minLevel: 70 },
  () => {
    stateToUrl();
    const p = new URLSearchParams(location.search);
    return p.get('map') === '1' && p.get('allRoutes') === '1' && p.get('minLevel') === '70'
      && !p.has('mapOpen') && !p.has('showAllRoutes');
  }));

check('url round-trips through state', (() => {
  history.replaceState(null, '',
    '?map=1&allRoutes=1&region=Zeah&calls=Port Sarim&corridor=0&trip=1~2');
  urlToState();
  const ok = state.mapOpen && state.showAllRoutes && state.region.has('Zeah')
    && state.calls.has('Port Sarim')
    && state.corridor === 0 && state.trip.join() === '1,2';
  history.replaceState(null, '', location.pathname);
  urlToState();
  return ok;
})());

/* ---- trip sequencing ---- */
const sample = [TASKS[0], TASKS[5], TASKS[12], TASKS[30]];
const trip = sequenceTrip(sample, null);

check('every task is picked up and delivered', (() => {
  const picks = trip.stops.flatMap((s) => s.picks).length;
  const drops = trip.stops.flatMap((s) => s.drops).length;
  return picks === sample.length && drops === sample.length;
})());
check('pickup always precedes delivery', (() => {
  const pickedAt = new Map();
  let ok = true;
  trip.stops.forEach((s, i) => {
    s.picks.forEach((t) => pickedAt.set(t.id, i));
    s.drops.forEach((t) => { if (!pickedAt.has(t.id) || pickedAt.get(t.id) > i) ok = false; });
  });
  return ok;
})());
check('consecutive visits to one port are merged',
  trip.stops.every((s, i) => i === 0 || s.port !== trip.stops[i - 1].port));
check('an empty trip has no stops', sequenceTrip([], null).stops.length === 0);
check('a named start port is honoured',
  sequenceTrip(sample, 'Lunar Isle').stops.length > 0);
check('distance is non-negative', trip.distance >= 0);
check('the route begins where the trip begins and holds every stop', (() => {
  const named = sequenceTrip(sample, 'Lunar Isle');
  return named.route[0] === 'Lunar Isle'
    && named.stops.every((s) => named.route.includes(s.port))
    && named.route.every((p, i) => i === 0 || p !== named.route[i - 1]);
})());

/* ---- what one more task would do to the trip ---- */
const tripIds = [TASKS[0].id, TASKS[5].id, TASKS[12].id, TASKS[30].id];
const withTrip = (fn) => withState({ trip: tripIds, tripStart: '' }, fn);
const known = (t) => t.xp !== null;

check('no trip means nothing to lift',
  withState({ trip: [], tripStart: '' }, () => xpLift(TASKS[0]) === null));
check('unknown xp cannot be priced',
  withTrip(() => TASKS.filter((t) => t.xp === null).every((t) => xpLift(t) === null)));

check('the lift is what re-pricing the trip says it is', withTrip(() => {
  const before = priceTrip(sample, null);
  const t = TASKS.filter((x) => known(x) && !tripIds.includes(x.id))[7];
  const after = priceTrip([...sample, t], null);
  const lift = xpLift(t);
  return near(lift.delta, after.rate - before.rate, 1e-9)
    && near(lift.base, before.rate, 1e-9)
    && near(lift.seconds, after.seconds - before.seconds, 1e-9);
}));

/* (X + x)/(S + s) > X/S reduces to x/s > X/S, so where a task costs time the
   sign of the lift is settled by the two rates alone - the claim the column
   makes. */
check('a task that costs time lifts the trip exactly when it out-rates it',
  withTrip(() => TASKS.every((t) => {
    const lift = xpLift(t);
    if (lift === null || lift.inTrip || lift.seconds <= 0) return true;
    const detour = (lift.xp / lift.seconds) * 3600;
    return Math.sign(Math.round(lift.delta * 1e6))
      === Math.sign(Math.round((detour - lift.base) * 1e6));
  })));

/* The stop order is greedy, so inserting a task can lead the planner to a
   better one and leave the longer trip quicker. Rare, but real: xp for free
   time can only lift the rate, whatever the task's own rate looks like. */
check('a task that saves time can only lift the trip', withTrip(() =>
  TASKS.filter(known).every((t) => {
    const lift = xpLift(t);
    return lift.seconds > 0 || lift.delta > 0;
  })));

check('a task in the trip reports what dropping it would cost', withTrip(() => {
  const t = TASK_BY_ID.get(tripIds[1]);
  const lift = xpLift(t);
  const without = priceTrip(sample.filter((x) => x.id !== t.id), null);
  return lift.inTrip && near(lift.rate, priceTrip(sample, null).rate, 1e-9)
    && near(lift.base, without.rate, 1e-9);
}));

check('the lift follows the trip it is measured against', (() => {
  const one = withState({ trip: tripIds, tripStart: '' }, () => xpLift(TASKS[1]).delta);
  const two = withState({ trip: tripIds.slice(0, 2), tripStart: '' },
    () => xpLift(TASKS[1]).delta);
  return one !== two;
})());

/* ---- what a board is worth stopping at ---- */
import { bestOfDraw, boardValues, detourFrom, POOLS } from '../../web/js/boards.js';

check('a flat pool is worth its one value however it is drawn',
  near(bestOfDraw([5, 5, 5, 5, 5, 5, 5, 5], 3, 1), 5, 1e-9));
check('taking every offer takes the whole pool',
  near(bestOfDraw([4, 3, 2, 1], 4, 4), 10, 1e-9));
check('worthless offers are dead draws, not absent ones', (() => {
  // the same two good tasks, buried in a pool of duds: the draw finds them
  // less often, so the board is worth less
  const rich = bestOfDraw([9, 7], 5, 1);
  const buried = bestOfDraw([9, 7, 0, 0, 0, 0, 0, 0, 0, 0], 5, 1);
  return buried < rich;
})());
check('more slots and more offers never hurt', (() => {
  const pool = [9, 8, 6, 5, 3, 2, 1];
  const rising = (f) => [1, 2, 3].every((i) => f(i) >= f(i - 1) - 1e-9);
  return rising((n) => bestOfDraw(pool, 4, n)) && rising((m) => bestOfDraw(pool, m + 2, 2));
})());

/* The formula is a hypergeometric identity, so the honest test of it is a
   draw. 40k shuffles of an eight-task pool, keeping the best two of three. */
const dealt = (() => {
  const pool = [90, 61, 44, 30, 21, 13, 8, 2];
  const runs = 40000;
  let total = 0;
  for (let r = 0; r < runs; r++) {
    const deck = pool.slice();
    for (let i = deck.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [deck[i], deck[j]] = [deck[j], deck[i]];
    }
    const hand = deck.slice(0, 3).sort((a, b) => b - a);
    total += hand[0] + hand[1];
  }
  return { pool, mean: total / runs, closed: bestOfDraw(pool, 3, 2) };
})();
check('the closed form matches dealing the cards',
  Math.abs(dealt.mean - dealt.closed) / dealt.closed < 0.02,
  `dealt ${dealt.mean.toFixed(1)} vs ${dealt.closed.toFixed(1)}`);

check('every board draws from a pool of its own tasks',
  [...POOLS.entries()].every(([board, pool]) => pool.every((t) => t.noticeBoard === board)));
check('no trip, no board values',
  withState({ trip: [] }, () => boardValues(TASKS).length === 0));
check('a board is worth less when fewer of its offers are usable', (() => {
  const all = withState({ trip: tripIds, freeSlots: 1 },
    () => new Map(boardValues(TASKS).map((b) => [b.port, b.value])));
  // the same trip, but only half the tasks pass the filters
  const half = withState({ trip: tripIds, freeSlots: 1 },
    () => new Map(boardValues(TASKS.filter((t) => t.id % 2 === 0)).map((b) => [b.port, b.value])));
  return [...half].every(([port, v]) => v <= all.get(port) + 1e-9)
    && [...all.values()].some((v) => v > 0);
})());
check('board values are sorted, best stop first',
  withState({ trip: tripIds, freeSlots: 1 }, () => {
    const vs = boardValues(TASKS).map((b) => b.value);
    return vs.every((v, i) => i === 0 || vs[i - 1] >= v);
  }));

/* The bug this replaced: a port halfway down a leg you already sail is a long
   way from either end of it, and the old measure - distance to the nearest
   stop - read that as a long trip out. Corsair Cove sits on the water between
   Catherby and Port Roberts; touching it costs about a tile. */
check('a port on the way is barely a detour', (() => {
  const onWay = detourFrom(['Catherby', 'Port Roberts'], 'Corsair Cove');
  const nearest = routeSeconds(Math.min(legDistance('Catherby', 'Corsair Cove'),
    legDistance('Corsair Cove', 'Port Roberts')), 0, 0);
  return onWay < 10 && nearest > 120;
})(), 'the case in the bug report');
check('a stop the trip already makes is no detour at all',
  detourFrom(['Catherby', 'Corsair Cove', 'Port Roberts'], 'Corsair Cove') === 0);
check('a port off the course costs sailing out and back', (() => {
  const off = detourFrom(['Catherby', 'Port Roberts'], 'Lunar Isle');
  return off > detourFrom(['Catherby', 'Port Roberts'], 'Corsair Cove');
})());
check('the detour is never negative, and never more than sailing out and back',
  allPorts.every((p) => {
    const route = ['Catherby', 'Port Sarim', 'Port Roberts'];
    const d = detourFrom(route, p);
    if (d === null) return true;
    const nearest = Math.min(...route.map((s) => legDistance(s, p) ?? Infinity));
    return d >= 0 && d <= routeSeconds(2 * nearest, 0, 0) + 1e-9;
  }));
check('an uncharted port has no detour to report',
  detourFrom(['Catherby', 'Port Roberts'], 'Atlantis') === null);
check('a route with nowhere to go reports nothing', detourFrom([], 'Catherby') === null);
check('every board is reported against the trip it is priced against',
  withState({ trip: tripIds, freeSlots: 1 },
    () => boardValues(TASKS).every((b) => b.detour === null || b.detour >= 0)));

/* ---- ports near the route ---- */
check('stops are never listed as passed', (() => {
  const near200 = portsNearRoute(trip.stops, 200);
  return trip.stops.every((s) => !near200.has(s.port));
})());
check('a wider corridor never finds fewer',
  portsNearRoute(trip.stops, 400).size >= portsNearRoute(trip.stops, 100).size);
check('a zero corridor finds nothing off-route', portsNearRoute(trip.stops, 0).size === 0);

const failed = results.filter((r) => !r.ok);
document.querySelector('#out').textContent =
  results.map((r) => `${r.ok ? 'ok  ' : 'FAIL'} ${r.name}${r.detail ? '  (' + r.detail + ')' : ''}`)
    .join('\n') + `\n\n${results.length - failed.length}/${results.length} passed`;
window.__results = results;
