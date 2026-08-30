/* Route builder: you choose tasks, this works out the stop order.

   Each task is a pickup at its origin then a delivery at its destination.
   Capacity is not modelled, so any number of cargos can be held at once; the
   only ordering rule is that a task's pickup precedes its delivery. */
import { $, esc } from './dom.js';
import { state } from './state.js';
import { TASK_BY_ID, LOCATIONS, portXY, hasBoardAt } from './ports.js';
import { courseBetween } from './course.js';
import { legDistance, routeSeconds, formatDuration, round, COST_NOTE }
  from './cost.js';

/** Shortest distance from point p to the segment a-b.

    The only geometry left in the app. It measures how close the course passes
    a port, which is a perpendicular offset from a line the ship really sails -
    not a stand-in for sailing distance, which the charted matrix now answers
    everywhere. */
export function distanceToSegment(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq === 0) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  // how far along the segment the nearest point lies, clamped to its ends
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lengthSq));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/* Charted sailing distance, so the stop order and the total both count the
   water a ship has to cover rather than the line a gull would take. */
const portGap = (a, b) => legDistance(a, b) ?? 0;

export const tripTasks = () => state.trip.map((id) => TASK_BY_ID.get(id)).filter(Boolean);

/** Nearest-neighbour over the pending pickups and the cargo currently held.
    Returns stops with consecutive visits to one port merged together. */
export function sequenceTrip(tasks, startPort) {
  if (!tasks.length) return { stops: [], distance: 0 };

  const waiting = new Set(tasks.map((t) => t.id));
  const held = new Set();
  let current = startPort || tasks[0].from;
  const visits = [];
  let travelled = 0;

  while (waiting.size || held.size) {
    let best = null;
    let bestDist = Infinity;
    const consider = (type, task, port) => {
      const d = portGap(current, port);
      if (d < bestDist) { bestDist = d; best = { type, task, port }; }
    };
    for (const id of waiting) consider('pick', TASK_BY_ID.get(id), TASK_BY_ID.get(id).from);
    for (const id of held) consider('drop', TASK_BY_ID.get(id), TASK_BY_ID.get(id).to);
    if (!best) break;

    if (best.type === 'pick') { waiting.delete(best.task.id); held.add(best.task.id); }
    else held.delete(best.task.id);

    travelled += bestDist;
    visits.push(best);
    current = best.port;
  }

  const stops = [];
  for (const visit of visits) {
    const last = stops[stops.length - 1];
    if (last && last.port === visit.port) {
      (visit.type === 'pick' ? last.picks : last.drops).push(visit.task);
    } else {
      stops.push({
        port: visit.port,
        picks: visit.type === 'pick' ? [visit.task] : [],
        drops: visit.type === 'drop' ? [visit.task] : [],
      });
    }
  }
  return { stops, distance: travelled };
}

/** Ports the route sails past without stopping -> Map(name -> {dist, leg}). */
export function portsNearRoute(stops, corridor) {
  // ?? not ||: a corridor of 0 is a real choice, not an absent one
  const limit = corridor ?? state.corridor;
  const stopping = new Set(stops.map((s) => s.port));

  // Measured against the water the ship actually sails, not the chord between
  // stops: a port can sit a long way off the straight line and still be passed
  // close, or sit right on it with a headland in between.
  const segments = [];
  for (let i = 1; i < stops.length; i++) {
    const course = courseBetween(stops[i - 1].port, stops[i].port);
    for (let j = 1; j < course.length; j++) segments.push([course[j - 1], course[j], i]);
  }

  const near = new Map();
  for (const name of Object.keys(LOCATIONS)) {
    if (stopping.has(name)) continue;
    const p = portXY(name);
    if (!p) continue;
    let best = Infinity;
    let bestLeg = null;
    for (const [a, b, i] of segments) {
      const d = distanceToSegment(p, a, b);
      if (d < best) { best = d; bestLeg = i; }
    }
    if (best <= limit) near.set(name, { dist: Math.round(best), leg: bestLeg });
  }
  return near;
}

/** Sequence a set of tasks and price the result: sailing, clock, and rate.

    One place, so the trip panel and the "what would this add" column cannot
    drift apart. Tasks with unknown XP count as zero, which makes the rate a
    floor rather than a guess. */
export function priceTrip(tasks, startPort) {
  const { stops, distance } = sequenceTrip(tasks, startPort);
  const xp = tasks.reduce((sum, t) => sum + (t.xp || 0), 0);
  // every task is loaded once and unloaded once, wherever the stops fall
  const seconds = routeSeconds(distance, stops.length, tasks.length * 2);
  const rate = seconds ? (xp / seconds) * 3600 : 0;
  return { tasks, stops, distance, xp, seconds, rate };
}

export function currentTrip() {
  return priceTrip(tripTasks(), state.tripStart || null);
}

/* ---- what one more task would do to the trip ----

   Re-sequences the whole trip with the candidate added and re-prices it. A
   task lying on water you were sailing anyway costs two cargo handlings and
   little else, so its XP lands nearly free and the trip's rate climbs; one
   that drags you off course pulls the rate down however good it looks alone.

   It is the lift under the greedy order the planner actually picks, not the
   best insertion the tour allows: we are ranking additions, not solving the
   travelling salesman. */

/** One cache per trip: the table asks for every visible row on each render,
    and the sort comparator asks again for every comparison. */
let lifts = { key: null, priced: null, values: new Map() };

// task ids are numbers, so a comma cannot be mistaken for part of one
const tripKey = () => `${state.trip.join(',')}|${state.tripStart}`;

/** How adding this task moves the trip's XP/hr, or null when there is no
    trip to move or the task's XP is unknown.

    A task already in the trip reports the same question read backwards: what
    the trip would lose without it. */
export function xpLift(task) {
  const key = tripKey();
  if (lifts.key !== key) lifts = { key, priced: null, values: new Map() };
  if (!lifts.values.has(task.id)) lifts.values.set(task.id, measureLift(task));
  return lifts.values.get(task.id);
}

function measureLift(task) {
  const tasks = tripTasks();
  // no trip to lift; the XP/hr column already answers the standalone case
  if (!tasks.length || task.xp === null) return null;

  const start = state.tripStart || null;
  const inTrip = tasks.some((t) => t.id === task.id);
  // the trip as it stands is one side of the comparison for every candidate
  const now = (lifts.priced ??= priceTrip(tasks, start));
  const before = inTrip ? priceTrip(tasks.filter((t) => t.id !== task.id), start) : now;
  const after = inTrip ? now : priceTrip([...tasks, task], start);

  return {
    inTrip,
    delta: after.rate - before.rate,
    base: before.rate,
    rate: after.rate,
    xp: task.xp,
    // usually positive - two cargo handlings at least - but not always: the
    // stop order is greedy, and inserting a task sometimes leads the planner
    // to a better one, so the longer trip can be the quicker one
    seconds: after.seconds - before.seconds,
  };
}

export function toggleTripTask(id) {
  if (state.trip.includes(id)) state.trip = state.trip.filter((x) => x !== id);
  else state.trip.push(id);
}

function passingHtml(stops) {
  const near = portsNearRoute(stops);
  const panel = $('#trip-passing');
  panel.toggleAttribute('hidden', near.size === 0);
  if (!near.size) return;

  const items = [...near.entries()]
    .sort((a, b) => a[1].dist - b[1].dist)
    .map(([name, v]) => {
      const board = hasBoardAt(name);
      // every passing port is clickable: cargo runs to and from ports that
      // have no board of their own, so the filter is worth offering there too
      const why = `${v.dist} tiles off leg ${v.leg}` +
        (board ? ', has a notice board' : ', no notice board') +
        ` - click for tasks to or from ${name}`;
      return `<button class="pass ${board ? 'has-board' : ''}` +
        `${state.calls.has(name) ? ' on' : ''}" data-port="${esc(name)}"` +
        ` title="${esc(why)}">${esc(name)} <i>${v.dist}</i>` +
        `${board ? ' &#10003;' : ''}</button>`;
    });

  panel.innerHTML = '<b>Sailing past</b> ' + items.join('') +
    '<span class="muted">Click a port to filter to the tasks that load or ' +
    'deliver there. &#10003; = notice board. Distances are to the charted ' +
    'course, so they measure how close you really sail.</span>';
}

export function renderTripPanel() {
  const { tasks, stops, distance: travelled, xp, seconds, rate } = currentTrip();
  $('#trip-panel').toggleAttribute('hidden', tasks.length === 0);
  if (!tasks.length) return;

  const unknown = tasks.filter((t) => t.xp === null).length;

  $('#trip-summary').innerHTML =
    `<span><b>${tasks.length}</b> task${tasks.length === 1 ? '' : 's'}</span>` +
    `<span><b>${stops.length}</b> stops</span>` +
    `<span>XP <b>${round(xp)}</b>` +
    (unknown ? ` <span class="unknown">+${unknown} unknown</span>` : '') + '</span>' +
    `<span>~<b>${round(travelled)}</b> tiles sailed</span>` +
    `<span title="${esc(COST_NOTE)}">~<b>${formatDuration(seconds)}</b></span>` +
    `<span title="${esc(COST_NOTE)}">XP/hr <b>${round(rate)}</b></span>`;

  const ports = [...new Set(tasks.flatMap((t) => [t.from, t.to]))].sort();
  $('#trip-start').innerHTML = '<option value="">Start anywhere</option>' +
    ports.map((p) => `<option value="${esc(p)}"${p === state.tripStart ? ' selected' : ''}>` +
      `${esc(p)}</option>`).join('');

  $('#trip-stops').innerHTML = stops.map((s, i) => {
    const acts = [
      ...s.picks.map((t) => `<span class="pick">load</span> ${t.qty} &rarr; ${esc(t.to)}`),
      ...s.drops.map((t) => `<span class="drop">deliver</span> ${t.qty} from ${esc(t.from)}` +
        (t.xp ? ` <b>${round(t.xp)}</b> xp` : '')),
    ];
    return `<li><span class="n">${i + 1}</span><span class="port">${esc(s.port)}</span>` +
      `<span class="acts">${acts.join('<br>')}</span></li>`;
  }).join('');

  passingHtml(stops);
}
