/* The results table and its CSV export. */
import { $, esc } from './dom.js';
import { state } from './state.js';
import { DERIVED, sorted } from './filters.js';
import { canRecoverAt, hasBoardAt } from './ports.js';
import { xpLift } from './trip.js';
import { legDistance, taskSeconds, taskXpPerHour, formatDuration, COST_NOTE } from './cost.js';

const COLUMN_COUNT = 14;

/** Cells that can be empty: unknown XP, or a pair the chart never measured. */
const num = (value, render) => (value === null || value === undefined
  ? '<span class="unknown">?</span>' : render(value));

const tick = (on, yes, no) => on
  ? `<span class="yes" title="${esc(yes)}">&#10004;</span>`
  : `<span class="no" title="${esc(no)}">&#10008;</span>`;

const round = (n) => Math.round(n).toLocaleString();

/** What this task does to the trip's XP/hr: the headline number, with the
    arithmetic behind it in the tooltip.

    Where the task costs time the sign follows from the rates alone: it lifts
    the trip exactly when its own rate beats the rate the trip already runs
    at. Where it saves time - the greedy stop order improving as it is
    inserted - it can only help. */
function liftCell(t) {
  const lift = xpLift(t);
  if (lift === null) return '<span class="unknown">&mdash;</span>';

  const worth = lift.seconds > 0
    ? `${lift.xp.toLocaleString()} xp for ${formatDuration(lift.seconds)} of the clock, ` +
      `a ${round((lift.xp / lift.seconds) * 3600)} xp/hr leg`
    : `${lift.xp.toLocaleString()} xp, and takes ${formatDuration(-lift.seconds)} off the ` +
      `clock: fitting it in leads the planner to a better stop order`;
  const why = lift.inTrip
    ? `Already in the trip: dropping it takes the rate from ${round(lift.rate)} to ` +
      `${round(lift.base)} xp/hr. It brings ${worth}.`
    : `Adding it takes the trip from ${round(lift.base)} to ${round(lift.rate)} xp/hr. ` +
      `It brings ${worth}.`;

  return `<span class="lift ${lift.delta < 0 ? 'down' : 'up'}" title="${esc(why)}">` +
    `${lift.delta < 0 ? '&minus;' : '+'}${round(Math.abs(lift.delta))}</span>`;
}

function rowHtml(t) {
  const inTrip = state.trip.includes(t.id);
  return `
    <tr class="${inTrip ? 'in-trip' : ''}">
      <td class="mid"><button class="trip-btn" data-id="${t.id}"
        title="${inTrip ? 'Remove from trip' : 'Add to trip'}">${inTrip ? '&minus;' : '+'}</button></td>
      <td class="num">${t.level}</td>
      <td><span class="tag ${t.direction}">${t.direction}</span></td>
      <td>${esc(t.noticeBoard)}</td>
      <td>${esc(t.from)}</td>
      <td>${esc(t.to)}</td>
      <td class="mid">${tick(canRecoverAt(t.from),
        `Shipwright at ${t.from}`, `No shipwright at ${t.from}`)}</td>
      <td class="mid">${tick(hasBoardAt(t.to),
        `Notice board at ${t.to}`, `No notice board at ${t.to}`)}</td>
      <td class="num">${t.qty}</td>
      <td class="num">${num(legDistance(t.from, t.to), (d) => Math.round(d).toLocaleString())}</td>
      <td class="num">${num(taskSeconds(t), (s) => formatDuration(s))}</td>
      <td class="num xp">${num(t.xp, (xp) => xp.toLocaleString())}</td>
      <td class="num rate">${num(taskXpPerHour(t), (r) => Math.round(r).toLocaleString())}</td>
      <td class="num">${liftCell(t)}</td>
    </tr>`;
}

export function renderTable(rows) {
  $('#tbody').innerHTML = rows.map(rowHtml).join('')
    || `<tr><td colspan="${COLUMN_COUNT}" class="empty">No tasks match these filters.</td></tr>`;

  const known = rows.filter((r) => r.xp !== null);
  const totalXp = known.reduce((sum, r) => sum + r.xp, 0);
  const best = known.length ? Math.max(...known.map((r) => r.xp)) : null;
  const rates = rows.map(taskXpPerHour).filter((r) => r !== null);
  const bestRate = rates.length ? Math.max(...rates) : null;

  $('#stats').innerHTML = `
    <span><b>${rows.length}</b> task${rows.length === 1 ? '' : 's'}</span>
    <span>total XP <b>${totalXp.toLocaleString()}</b></span>
    <span>avg XP <b>${known.length ? Math.round(totalXp / known.length).toLocaleString() : '&mdash;'}</b></span>
    <span>best <b>${best === null ? '&mdash;' : best.toLocaleString()}</b></span>
    <span title="${esc(COST_NOTE)}">best XP/hr <b>${
      bestRate === null ? '&mdash;' : Math.round(bestRate).toLocaleString()}</b></span>`;

  document.querySelectorAll('th[data-key]').forEach((th) => {
    th.classList.toggle('sorted', th.dataset.key === state.sortKey);
    th.dataset.dir = th.dataset.key === state.sortKey ? state.sortDir : '';
  });
}

// wider than the table: region is useful in a spreadsheet even though the
// page no longer shows it, and the CSV can afford the width
const CSV_COLUMNS = ['level', 'direction', 'noticeBoard', 'from', 'to', 'recover', 'tasks',
                     'fromRegion', 'toRegion', 'cargo', 'qty', 'distance', 'seconds',
                     'xp', 'xpPerHour', 'lift'];

const CSV_DERIVED = {
  ...DERIVED,
  recover: (t) => (canRecoverAt(t.from) ? 'yes' : 'no'),
  tasks: (t) => (hasBoardAt(t.to) ? 'yes' : 'no'),
  distance: (t) => { const d = legDistance(t.from, t.to); return d === null ? null : d.toFixed(1); },
  seconds: (t) => { const s = taskSeconds(t); return s === null ? null : s.toFixed(1); },
  xpPerHour: (t) => { const r = taskXpPerHour(t); return r === null ? null : Math.round(r); },
  lift: (t) => { const l = xpLift(t); return l === null ? null : Math.round(l.delta); },
};

export function exportCsv(rows) {
  const cell = (t, column) => {
    const raw = CSV_DERIVED[column] ? CSV_DERIVED[column](t) : t[column];
    const value = raw === null ? '' : String(raw);
    return /[",]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
  };

  const csv = [CSV_COLUMNS.join(',')]
    .concat(sorted(rows).map((t) => CSV_COLUMNS.map((c) => cell(t, c)).join(',')))
    .join('\n');

  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'port_tasks_filtered.csv';
  link.click();
  URL.revokeObjectURL(url);
}
