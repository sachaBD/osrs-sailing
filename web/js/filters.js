/* Turning the state into the list of tasks on screen. */
import { state } from './state.js';
import { TASKS, legsOf, regionOf, oceansOf, canRecoverAt, hasBoardAt } from './ports.js';
import { legDistance, taskSeconds, taskXpPerHour } from './cost.js';

/** Columns computed from the port tables rather than stored on the task.
    Region is no longer a column, but it stays here for the CSV export. */
export const DERIVED = {
  fromRegion: (t) => regionOf(t.from),
  toRegion: (t) => regionOf(t.to),
  recover: (t) => (canRecoverAt(t.from) ? 1 : 0),
  tasks: (t) => (hasBoardAt(t.to) ? 1 : 0),
  distance: (t) => legDistance(t.from, t.to),
  seconds: (t) => taskSeconds(t),
  xpPerHour: (t) => taskXpPerHour(t),
};

/** Does this task touch the selected group, under the current scope?
    `valuesFor` maps a port to the groups it belongs to (1 region, 1+ oceans). */
export function matchesScope(task, selected, valuesFor) {
  if (selected.size === 0) return true;
  const hit = (port) => valuesFor(port).some((v) => selected.has(v));
  const { board, from, to } = legsOf(task);
  switch (state.scope) {
    case 'board': return hit(board);
    case 'from': return hit(from);
    case 'to': return hit(to);
    case 'both': return hit(from) && hit(to);
    default: return hit(board) || hit(from) || hit(to);
  }
}

export function filtered() {
  const q = state.q.trim().toLowerCase();
  const xpBounded = state.minXp !== null || state.maxXp !== null;

  return TASKS.filter((t) => {
    if (t.level < state.minLevel || t.level > state.maxLevel) return false;
    if (state.board && t.noticeBoard !== state.board) return false;
    if (state.direction && t.direction !== state.direction) return false;
    // origin and destination are direct membership tests; only region, ocean
    // and map-selected ports honour the "Match on" scope
    if (state.from.size && !state.from.has(t.from)) return false;
    if (state.to.size && !state.to.has(t.to)) return false;
    if (!matchesScope(t, state.region, (p) => [regionOf(p)])) return false;
    if (!matchesScope(t, state.ocean, oceansOf)) return false;
    if (!matchesScope(t, state.port, (p) => [p])) return false;
    if (state.recoverAtOrigin && !canRecoverAt(t.from)) return false;
    if (state.boardAtDest && !hasBoardAt(t.to)) return false;
    // unknown XP cannot satisfy a numeric bound, so any XP filter excludes it
    if ((state.hideUnknownXp || xpBounded) && t.xp === null) return false;
    if (state.minXp !== null && t.xp < state.minXp) return false;
    if (state.maxXp !== null && t.xp > state.maxXp) return false;
    if (q && !`${t.noticeBoard} ${t.from} ${t.to}`.toLowerCase().includes(q)) return false;
    return true;
  });
}

export function sorted(rows) {
  const key = state.sortKey;
  const dir = state.sortDir === 'asc' ? 1 : -1;
  const derived = DERIVED[key];

  return [...rows].sort((a, b) => {
    const av = derived ? derived(a) : a[key];
    const bv = derived ? derived(b) : b[key];
    // nulls (unknown XP) always sink to the bottom, whichever way we sort
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    if (typeof av === 'string') return av.localeCompare(bv) * dir;
    return (av - bv) * dir;
  });
}
