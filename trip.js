/* Route builder: you choose tasks, this works out the stop order.

   Each task is a pickup at its origin then a delivery at its destination.
   Capacity is not modelled, so any number of cargos can be held at once; the
   only ordering rule is that a task's pickup comes before its delivery. */

// window.PORT_TASKS, not app.js's TASKS: this file is evaluated first
const TASK_BY_ID = new Map(window.PORT_TASKS.map((t) => [t.id, t]));

const portXY = (name) => {
  const c = (LOCATIONS[name] || {}).coords;
  if (!c) return null;
  const [x, y] = c.split(',').map(Number);
  return [x, y];
};

/** Straight-line distance in game tiles. Real sailing goes around land, so this
    is a rough comparator between orderings, not a travel-time estimate. */
function portDistance(a, b) {
  const p = portXY(a);
  const q = portXY(b);
  if (!p || !q) return 0;
  return Math.hypot(p[0] - q[0], p[1] - q[1]);
}

/* Default width of the "on the way" corridor, in game tiles; adjustable in the
   trip panel. The whole map spans about 1,700 tiles. */
const ROUTE_CORRIDOR = 120;

/** Shortest distance from point p to the segment a-b. */
function distanceToSegment(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  // how far along the segment the nearest point lies, clamped to its ends
  let t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

/** Ports the route sails past without stopping -> {name: {dist, leg}}. */
function portsNearRoute(stops, corridor) {
  const limit = corridor || state.corridor || ROUTE_CORRIDOR;
  const stopping = new Set(stops.map((s) => s.port));
  const legs = [];
  for (let i = 1; i < stops.length; i++) {
    const a = portXY(stops[i - 1].port);
    const b = portXY(stops[i].port);
    if (a && b) legs.push([a, b, i]);
  }

  const near = new Map();
  for (const name of Object.keys(LOCATIONS)) {
    if (stopping.has(name)) continue;
    const p = portXY(name);
    if (!p) continue;
    let best = Infinity;
    let bestLeg = null;
    for (const [a, b, i] of legs) {
      const d = distanceToSegment(p, a, b);
      if (d < best) { best = d; bestLeg = i; }
    }
    if (best <= limit) near.set(name, { dist: Math.round(best), leg: bestLeg });
  }
  return near;
}

function tripTasks() {
  return state.trip.map((id) => TASK_BY_ID.get(id)).filter(Boolean);
}

/** Nearest-neighbour over the pending pickups and the deliveries now carried.
    Returns [{port, picks:[task], drops:[task], leg}], consecutive visits to the
    same port merged into one stop. */
function sequenceTrip(tasks, startPort) {
  if (!tasks.length) return { stops: [], distance: 0 };

  const waiting = new Set(tasks.map((t) => t.id));
  const held = new Set();
  let current = startPort || tasks[0].from;
  const visits = [];
  let distance = 0;

  while (waiting.size || held.size) {
    let best = null;
    let bestDist = Infinity;
    const consider = (type, task, port) => {
      const d = portDistance(current, port);
      if (d < bestDist) { bestDist = d; best = { type, task, port }; }
    };
    for (const id of waiting) consider('pick', TASK_BY_ID.get(id), TASK_BY_ID.get(id).from);
    for (const id of held) consider('drop', TASK_BY_ID.get(id), TASK_BY_ID.get(id).to);
    if (!best) break;

    if (best.type === 'pick') { waiting.delete(best.task.id); held.add(best.task.id); }
    else held.delete(best.task.id);

    distance += bestDist;
    visits.push({ port: best.port, type: best.type, task: best.task, leg: bestDist });
    current = best.port;
  }

  // merge runs of visits to the same port into a single stop
  const stops = [];
  for (const v of visits) {
    const last = stops[stops.length - 1];
    if (last && last.port === v.port) {
      (v.type === 'pick' ? last.picks : last.drops).push(v.task);
    } else {
      stops.push({
        port: v.port,
        leg: v.leg,
        picks: v.type === 'pick' ? [v.task] : [],
        drops: v.type === 'drop' ? [v.task] : [],
      });
    }
  }
  return { stops, distance };
}

function currentTrip() {
  const tasks = tripTasks();
  return { tasks, ...sequenceTrip(tasks, state.tripStart || null) };
}

function addToTrip(id) {
  if (!state.trip.includes(id)) state.trip.push(id);
  render();
}

function removeFromTrip(id) {
  state.trip = state.trip.filter((x) => x !== id);
  render();
}

function clearTrip() {
  state.trip = [];
  state.tripStart = '';
  render();
}

/** Fill the trip panel: ordered stops, plus XP and rough distance totals. */
function renderTrip() {
  const panel = document.querySelector('#trip-panel');
  const { tasks, stops, distance } = currentTrip();

  panel.toggleAttribute('hidden', tasks.length === 0);
  if (!tasks.length) return;

  const xp = tasks.reduce((s, t) => s + (t.xp || 0), 0);
  const unknown = tasks.filter((t) => t.xp === null).length;

  document.querySelector('#trip-summary').innerHTML =
    '<span><b>' + tasks.length + '</b> task' + (tasks.length === 1 ? '' : 's') + '</span>' +
    '<span><b>' + stops.length + '</b> stops</span>' +
    '<span>XP <b>' + xp.toLocaleString() + '</b>' +
    (unknown ? ' <span class="unknown">+' + unknown + ' unknown</span>' : '') + '</span>' +
    '<span>~<b>' + Math.round(distance).toLocaleString() + '</b> tiles sailed</span>';

  const startSel = document.querySelector('#trip-start');
  const ports = [...new Set(tasks.flatMap((t) => [t.from, t.to]))].sort();
  startSel.innerHTML = '<option value="">Start anywhere</option>' +
    ports.map((p) => '<option value="' + p + '"' +
      (p === state.tripStart ? ' selected' : '') + '>' + p + '</option>').join('');

  const near = portsNearRoute(stops);
  const passing = document.querySelector('#trip-passing');
  passing.toggleAttribute('hidden', near.size === 0);
  if (near.size) {
    const items = [...near.entries()].sort((a, b) => a[1].dist - b[1].dist).map(([name, v]) => {
      const board = (LOCATIONS[name] || {}).notice_board === 'yes';
      return '<span class="pass' + (board ? ' has-board' : '') + '" title="' +
        v.dist + ' tiles off leg ' + v.leg +
        (board ? ', has a notice board' : ', no notice board') + '">' +
        name + ' <i>' + v.dist + '</i>' + (board ? ' &#10003;' : '') + '</span>';
    });
    passing.innerHTML = '<b>Sailing past</b> ' + items.join('') +
      '<span class="muted">&#10003; = notice board. Distances are to the ' +
      'straight line between stops, which ignores land.</span>';
  }

  document.querySelector('#trip-stops').innerHTML = stops.map((s, i) => {
    const bits = [];
    for (const t of s.picks) {
      bits.push('<span class="pick">load</span> ' + t.qty + ' &rarr; ' + t.to);
    }
    for (const t of s.drops) {
      bits.push('<span class="drop">deliver</span> ' + t.qty + ' from ' + t.from +
        (t.xp ? ' <b>' + t.xp.toLocaleString() + '</b> xp' : ''));
    }
    return '<li><span class="n">' + (i + 1) + '</span>' +
      '<span class="port">' + s.port + '</span>' +
      '<span class="acts">' + bits.join('<br>') + '</span></li>';
  }).join('');
}
