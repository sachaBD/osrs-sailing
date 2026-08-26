const TASKS = window.PORT_TASKS;
const LOCATIONS = window.PORT_LOCATIONS;

const regionOf = (loc) => (LOCATIONS[loc] || {}).region || 'Unknown';
const oceansOf = (loc) => (LOCATIONS[loc] || {}).oceans || [];
// A shipwright is what lets you recover a capsized or parked boat.
const canRecoverAt = (loc) => (LOCATIONS[loc] || {}).shipwright === 'yes';
const dockLevelOf = (loc) => Number((LOCATIONS[loc] || {}).dock_level) || 0;

// The three ports a task touches, in the order the "Match on" scope names them.
const legsOf = (t) => ({ board: t.noticeBoard, from: t.from, to: t.to });

const state = {
  sortKey: 'xp',
  sortDir: 'desc',
  q: '',
  board: '',
  from: new Set(),
  to: new Set(),
  region: new Set(),
  ocean: new Set(),
  scope: 'any',
  cargo: '',
  direction: '',
  minLevel: 1,
  maxLevel: 99,
  minXp: null,
  maxXp: null,
  hideUnknownXp: false,
  recoverAtDest: false,
};

const $ = (s) => document.querySelector(s);
const uniq = (key) => [...new Set(TASKS.map((t) => t[key]))].sort((a, b) => a.localeCompare(b));
const allLocations = [...new Set(TASKS.flatMap((t) => [t.noticeBoard, t.from, t.to]))].sort((a, b) => a.localeCompare(b));

function fillSelect(id, values, placeholder) {
  const el = $(id);
  el.innerHTML = `<option value="">${placeholder}</option>` +
    values.map((v) => `<option value="${v}">${v}</option>`).join('');
}

/* A dropdown of checkboxes backed by a Set in `state`. */
function multiSelect(rootId, values, placeholder, key) {
  const root = $(rootId);
  const selected = state[key];
  root.innerHTML = `
    <button type="button" class="ms-button"><span class="ms-label">${placeholder}</span><span class="ms-caret">▾</span></button>
    <div class="ms-menu" hidden>
      <div class="ms-actions"><button type="button" data-act="all">All</button><button type="button" data-act="none">None</button></div>
      <div class="ms-options">${values.map((v) =>
        `<label><input type="checkbox" value="${v}"><span>${v}</span></label>`).join('')}</div>
    </div>`;

  const button = root.querySelector('.ms-button');
  const menu = root.querySelector('.ms-menu');
  const label = root.querySelector('.ms-label');

  const syncLabel = () => {
    label.textContent = selected.size === 0 ? placeholder
      : selected.size === 1 ? [...selected][0]
      : `${selected.size} selected`;
    button.classList.toggle('active', selected.size > 0);
  };

  button.addEventListener('click', () => {
    const opening = menu.hidden;
    document.querySelectorAll('.ms-menu').forEach((m) => { m.hidden = true; });
    menu.hidden = !opening;
  });

  menu.addEventListener('change', (e) => {
    if (e.target.checked) selected.add(e.target.value); else selected.delete(e.target.value);
    syncLabel();
    render();
  });

  menu.querySelector('.ms-actions').addEventListener('click', (e) => {
    const act = e.target.dataset.act;
    if (!act) return;
    selected.clear();
    if (act === 'all') values.forEach((v) => selected.add(v));
    menu.querySelectorAll('input').forEach((i) => { i.checked = act === 'all'; });
    syncLabel();
    render();
  });

  root._reset = () => {
    selected.clear();
    menu.querySelectorAll('input').forEach((i) => { i.checked = false; });
    menu.hidden = true;
    syncLabel();
  };
  syncLabel();
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.ms')) document.querySelectorAll('.ms-menu').forEach((m) => { m.hidden = true; });
});

/* Does this task touch the selected group, under the current scope?
   `valuesFor` maps a port name to the groups it belongs to (1 region, 1+ oceans). */
function matchesScope(t, selected, valuesFor) {
  if (selected.size === 0) return true;
  const hit = (loc) => valuesFor(loc).some((v) => selected.has(v));
  const { board, from, to } = legsOf(t);
  switch (state.scope) {
    case 'board': return hit(board);
    case 'from': return hit(from);
    case 'to': return hit(to);
    case 'both': return hit(from) && hit(to);
    default: return hit(board) || hit(from) || hit(to);
  }
}

function filtered() {
  const q = state.q.trim().toLowerCase();
  const xpBounded = state.minXp !== null || state.maxXp !== null;
  return TASKS.filter((t) => {
    if (t.level < state.minLevel || t.level > state.maxLevel) return false;
    if (state.board && t.noticeBoard !== state.board) return false;
    if (state.from.size && !state.from.has(t.from)) return false;
    if (state.to.size && !state.to.has(t.to)) return false;
    if (state.cargo && t.cargo !== state.cargo) return false;
    if (!matchesScope(t, state.region, (l) => [regionOf(l)])) return false;
    if (!matchesScope(t, state.ocean, oceansOf)) return false;
    if (state.recoverAtDest && !canRecoverAt(t.to)) return false;
    if (state.direction && t.direction !== state.direction) return false;
    // unknown XP can't satisfy a numeric bound, so an XP filter excludes it
    if ((state.hideUnknownXp || xpBounded) && t.xp === null) return false;
    if (state.minXp !== null && t.xp < state.minXp) return false;
    if (state.maxXp !== null && t.xp > state.maxXp) return false;
    if (q) {
      const hay = `${t.noticeBoard} ${t.from} ${t.to} ${t.cargo}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

// Table columns computed from the location table rather than stored on the task.
const DERIVED = {
  fromRegion: (r) => regionOf(r.from),
  toRegion: (r) => regionOf(r.to),
  recover: (r) => (canRecoverAt(r.to) ? 1 : 0),
  destDockLevel: (r) => dockLevelOf(r.to),
};

function sorted(rows) {
  const k = state.sortKey;
  const dir = state.sortDir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const derived = DERIVED[k];
    const av = derived ? derived(a) : a[k];
    const bv = derived ? derived(b) : b[k];
    // nulls (unknown XP) always sink to the bottom
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    if (typeof av === 'string') return av.localeCompare(bv) * dir;
    return (av - bv) * dir;
  });
}

function render() {
  const rows = sorted(filtered());
  const known = rows.filter((r) => r.xp !== null);
  const totalXp = known.reduce((s, r) => s + r.xp, 0);

  $('#stats').innerHTML = `
    <span><b>${rows.length}</b> task${rows.length === 1 ? '' : 's'}</span>
    <span>total XP <b>${totalXp.toLocaleString()}</b></span>
    <span>avg XP <b>${known.length ? Math.round(totalXp / known.length).toLocaleString() : '—'}</b></span>
    <span>best <b>${known.length ? known.reduce((m, r) => (r.xp > m.xp ? r : m)).xp.toLocaleString() : '—'}</b></span>`;

  $('#tbody').innerHTML = rows.map((t) => `
    <tr>
      <td class="num">${t.level}</td>
      <td class="num xp">${t.xp === null ? '<span class="unknown">?</span>' : t.xp.toLocaleString()}</td>
      <td>${t.noticeBoard}</td>
      <td>${t.from}</td>
      <td class="muted">${regionOf(t.from)}</td>
      <td>${t.to}</td>
      <td class="muted">${regionOf(t.to)}</td>
      <td class="mid">${canRecoverAt(t.to)
        ? '<span class="yes" title="Shipwright at ' + t.to + '">✔</span>'
        : '<span class="no" title="No shipwright at ' + t.to + '">✘</span>'}</td>
      <td>${t.cargo}</td>
      <td class="num">${t.qty}</td>
      <td class="num">${t.xpPerQty === null ? '<span class="unknown">?</span>' : t.xpPerQty.toLocaleString()}</td>
      <td><span class="tag ${t.direction}">${t.direction}</span></td>
    </tr>`).join('') || '<tr><td colspan="12" class="empty">No tasks match these filters.</td></tr>';

  document.querySelectorAll('th[data-key]').forEach((th) => {
    th.classList.toggle('sorted', th.dataset.key === state.sortKey);
    th.dataset.dir = th.dataset.key === state.sortKey ? state.sortDir : '';
  });
}

function bind(id, key, transform = (v) => v) {
  $(id).addEventListener('input', (e) => {
    state[key] = transform(e.target.type === 'checkbox' ? e.target.checked : e.target.value);
    render();
  });
}

const numOr = (fallback) => (v) => (v === '' ? fallback : Number(v));

fillSelect('#f-board', allLocations, 'Any notice board');
fillSelect('#f-cargo', uniq('cargo'), 'Any cargo');
multiSelect('#f-from', allLocations, 'Any origin', 'from');
multiSelect('#f-region', [...new Set(Object.values(LOCATIONS).map((v) => v.region))].sort(), 'Any region', 'region');
multiSelect('#f-ocean', [...new Set(Object.values(LOCATIONS).flatMap((v) => v.oceans))].sort(), 'Any ocean', 'ocean');
multiSelect('#f-to', allLocations, 'Any destination', 'to');

bind('#f-q', 'q');
bind('#f-board', 'board');
bind('#f-cargo', 'cargo');
bind('#f-direction', 'direction');
bind('#f-scope', 'scope');
bind('#f-unknown', 'hideUnknownXp');
bind('#f-recover', 'recoverAtDest');
bind('#f-min', 'minLevel', numOr(1));
bind('#f-max', 'maxLevel', numOr(99));
bind('#f-xpmin', 'minXp', numOr(null));
bind('#f-xpmax', 'maxXp', numOr(null));

document.querySelectorAll('th[data-key]').forEach((th) => {
  th.addEventListener('click', () => {
    const k = th.dataset.key;
    if (state.sortKey === k) {
      state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      state.sortKey = k;
      state.sortDir = th.dataset.default || 'desc';
    }
    render();
  });
});

$('#reset').addEventListener('click', () => {
  Object.assign(state, {
    q: '', board: '', cargo: '', direction: '', scope: 'any',
    minLevel: 1, maxLevel: 99, minXp: null, maxXp: null,
    hideUnknownXp: false, recoverAtDest: false,
  });
  document.querySelectorAll('.filters input, .filters select').forEach((el) => {
    if (el.type === 'checkbox') el.checked = false;
    else el.value = '';
  });
  $('#f-scope').value = 'any';
  document.querySelectorAll('.ms').forEach((ms) => ms._reset());
  render();
});

$('#export').addEventListener('click', () => {
  const rows = sorted(filtered());
  const cols = ['level', 'xp', 'noticeBoard', 'from', 'fromRegion', 'to', 'toRegion',
                'cargo', 'qty', 'xpPerQty', 'direction', 'recover'];
  const derived = { ...DERIVED, recover: (r) => (canRecoverAt(r.to) ? 'yes' : 'no') };
  const csv = [cols.join(',')].concat(
    rows.map((r) => cols.map((c) => {
      const raw = derived[c] ? derived[c](r) : r[c];
      const v = raw === null ? '' : String(raw);
      return /[",]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
    }).join(','))
  ).join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'port_tasks_filtered.csv';
  a.click();
  URL.revokeObjectURL(url);
});

render();
