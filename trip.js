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
