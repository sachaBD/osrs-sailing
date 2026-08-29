/* The results table and its CSV export. */
import { $, esc } from './dom.js';
import { state } from './state.js';
import { DERIVED, sorted } from './filters.js';
import { regionOf, canRecoverAt, hasBoardAt } from './ports.js';

const COLUMN_COUNT = 12;

const tick = (on, yes, no) => on
  ? `<span class="yes" title="${esc(yes)}">&#10004;</span>`
  : `<span class="no" title="${esc(no)}">&#10008;</span>`;

function rowHtml(t) {
  const inTrip = state.trip.includes(t.id);
  return `
    <tr class="${inTrip ? 'in-trip' : ''}">
      <td class="mid"><button class="trip-btn" data-id="${t.id}"
        title="${inTrip ? 'Remove from trip' : 'Add to trip'}">${inTrip ? '&minus;' : '+'}</button></td>
      <td class="num">${t.level}</td>
      <td class="num xp">${t.xp === null ? '<span class="unknown">?</span>' : t.xp.toLocaleString()}</td>
      <td>${esc(t.noticeBoard)}</td>
      <td>${esc(t.from)}</td>
      <td class="muted">${esc(regionOf(t.from))}</td>
      <td class="mid">${tick(canRecoverAt(t.from),
        `Shipwright at ${t.from}`, `No shipwright at ${t.from}`)}</td>
      <td>${esc(t.to)}</td>
      <td class="muted">${esc(regionOf(t.to))}</td>
      <td class="mid">${tick(hasBoardAt(t.to),
        `Notice board at ${t.to}`, `No notice board at ${t.to}`)}</td>
      <td class="num">${t.qty}</td>
      <td><span class="tag ${t.direction}">${t.direction}</span></td>
    </tr>`;
}

export function renderTable(rows) {
  $('#tbody').innerHTML = rows.map(rowHtml).join('')
    || `<tr><td colspan="${COLUMN_COUNT}" class="empty">No tasks match these filters.</td></tr>`;

  const known = rows.filter((r) => r.xp !== null);
  const totalXp = known.reduce((sum, r) => sum + r.xp, 0);
  const best = known.length ? Math.max(...known.map((r) => r.xp)) : null;

  $('#stats').innerHTML = `
    <span><b>${rows.length}</b> task${rows.length === 1 ? '' : 's'}</span>
    <span>total XP <b>${totalXp.toLocaleString()}</b></span>
    <span>avg XP <b>${known.length ? Math.round(totalXp / known.length).toLocaleString() : '&mdash;'}</b></span>
    <span>best <b>${best === null ? '&mdash;' : best.toLocaleString()}</b></span>`;

  document.querySelectorAll('th[data-key]').forEach((th) => {
    th.classList.toggle('sorted', th.dataset.key === state.sortKey);
    th.dataset.dir = th.dataset.key === state.sortKey ? state.sortDir : '';
  });
}

const CSV_COLUMNS = ['level', 'xp', 'noticeBoard', 'from', 'fromRegion', 'recover',
                     'to', 'toRegion', 'board', 'qty', 'direction'];

const CSV_DERIVED = {
  ...DERIVED,
  recover: (t) => (canRecoverAt(t.from) ? 'yes' : 'no'),
  board: (t) => (hasBoardAt(t.to) ? 'yes' : 'no'),
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
