/* Unit tests for the pure logic, run inside a real browser by js_test.py.
   Anything needing the DOM or the map belongs in smoke_test.py instead. */
import { esc } from '../src/dom.js';
import { distance, distanceToSegment } from '../src/geometry.js';
import {
  TASKS, TASK_BY_ID, allPorts, allRegions, allOceans,
  regionOf, oceansOf, canRecoverAt, hasBoardAt, portXY, legsOf,
} from '../src/ports.js';
import { state } from '../src/state.js';
import { filtered, sorted, matchesScope } from '../src/filters.js';
import { sequenceTrip, portsNearRoute } from '../src/trip.js';

const results = [];
const check = (name, cond, detail = '') => results.push({ name, ok: !!cond, detail });
const near = (a, b, tol = 0.001) => Math.abs(a - b) < tol;

/* ---- dom ---- */
check('esc neutralises quotes', esc(`Land's "End" & <b>`) === 'Land&#39;s &quot;End&quot; &amp; &lt;b&gt;');

/* ---- geometry ---- */
check('distance is euclidean', near(distance([0, 0], [3, 4]), 5));
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
check('sorting nulls sink regardless of direction', (() => {
  const rows = TASKS.slice();
  const desc = withState({ sortKey: 'xp', sortDir: 'desc' }, () => sorted(rows));
  const asc = withState({ sortKey: 'xp', sortDir: 'asc' }, () => sorted(rows));
  return desc[desc.length - 1].xp === null && asc[asc.length - 1].xp === null;
})());

/* ---- URL parameter names are a public surface: links get shared ---- */
import { stateToUrl, urlToState } from '../src/state.js';

check('url uses the published parameter names', withState(
  { mapOpen: true, showAllRoutes: true, minLevel: 70 },
  () => {
    stateToUrl();
    const p = new URLSearchParams(location.search);
    return p.get('map') === '1' && p.get('allRoutes') === '1' && p.get('minLevel') === '70'
      && !p.has('mapOpen') && !p.has('showAllRoutes');
  }));

check('url round-trips through state', (() => {
  history.replaceState(null, '', '?map=1&allRoutes=1&region=Zeah&corridor=0&trip=1~2');
  urlToState();
  const ok = state.mapOpen && state.showAllRoutes && state.region.has('Zeah')
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
