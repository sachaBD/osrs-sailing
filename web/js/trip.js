/* Route builder: you choose tasks, this works out the stop order.

   Each task is a pickup at its origin then a delivery at its destination.
   Capacity is not modelled, so any number of cargos can be held at once; the
   only ordering rule is that a task's pickup precedes its delivery. */
import { $, esc } from './dom.js';
import { state } from './state.js';
import { TASK_BY_ID, LOCATIONS, portXY, hasBoardAt } from './ports.js';
import { distanceToSegment } from './geometry.js';
import { courseBetween } from './course.js';
import { legDistance } from './cost.js';

/** Default width of the "on the way" corridor, in game tiles; adjustable in
    the trip panel. The whole map spans about 1,700 tiles. */
export const ROUTE_CORRIDOR = 120;

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
  const limit = corridor ?? state.corridor ?? ROUTE_CORRIDOR;
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

export function currentTrip() {
  const tasks = tripTasks();
  return { tasks, ...sequenceTrip(tasks, state.tripStart || null) };
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
      const why = `${v.dist} tiles off leg ${v.leg}` +
        (board ? ', has a notice board' : ', no notice board');
      return `<span class="pass ${board ? 'has-board' : ''}" title="${esc(why)}">` +
        `${esc(name)} <i>${v.dist}</i>${board ? ' &#10003;' : ''}</span>`;
    });

  panel.innerHTML = '<b>Sailing past</b> ' + items.join('') +
    '<span class="muted">&#10003; = notice board. Distances are to the charted ' +
    'course, so they measure how close you really sail.</span>';
}

export function renderTripPanel() {
  const { tasks, stops, distance: travelled } = currentTrip();
  $('#trip-panel').toggleAttribute('hidden', tasks.length === 0);
  if (!tasks.length) return;

  const xp = tasks.reduce((sum, t) => sum + (t.xp || 0), 0);
  const unknown = tasks.filter((t) => t.xp === null).length;

  $('#trip-summary').innerHTML =
    `<span><b>${tasks.length}</b> task${tasks.length === 1 ? '' : 's'}</span>` +
    `<span><b>${stops.length}</b> stops</span>` +
    `<span>XP <b>${xp.toLocaleString()}</b>` +
    (unknown ? ` <span class="unknown">+${unknown} unknown</span>` : '') + '</span>' +
    `<span>~<b>${Math.round(travelled).toLocaleString()}</b> tiles sailed</span>`;

  const ports = [...new Set(tasks.flatMap((t) => [t.from, t.to]))].sort();
  $('#trip-start').innerHTML = '<option value="">Start anywhere</option>' +
    ports.map((p) => `<option value="${esc(p)}"${p === state.tripStart ? ' selected' : ''}>` +
      `${esc(p)}</option>`).join('');

  $('#trip-stops').innerHTML = stops.map((s, i) => {
    const acts = [
      ...s.picks.map((t) => `<span class="pick">load</span> ${t.qty} &rarr; ${esc(t.to)}`),
      ...s.drops.map((t) => `<span class="drop">deliver</span> ${t.qty} from ${esc(t.from)}` +
        (t.xp ? ` <b>${t.xp.toLocaleString()}</b> xp` : '')),
    ];
    return `<li><span class="n">${i + 1}</span><span class="port">${esc(s.port)}</span>` +
      `<span class="acts">${acts.join('<br>')}</span></li>`;
  }).join('');

  passingHtml(stops);
}
