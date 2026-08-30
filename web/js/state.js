/* The view's whole state, plus its serialisation.

   Modules mutate `state` then call `update()`; main.js subscribes the renderer.
   Going through a subscription rather than importing the renderer keeps the
   module graph acyclic. */
import { TASK_BY_ID } from './ports.js';
import { store, stored } from './dom.js';

export const state = {
  sortKey: 'xp',
  sortDir: 'desc',
  q: '',
  board: '',
  direction: '',
  scope: 'any',
  minLevel: 1,
  maxLevel: 99,
  minXp: null,
  maxXp: null,
  hideUnknownXp: false,
  recoverAtOrigin: false,
  boardAtDest: false,
  showAllRoutes: false,
  corridor: 120,        // "sailing past" radius, in game tiles
  freeSlots: 1,         // room in the hold, which is what a board stop fills
  mapOpen: false,
  from: new Set(),
  to: new Set(),
  calls: new Set(),     // ports a task touches at either end
  region: new Set(),
  ocean: new Set(),
  trip: [],             // ordered task ids in the route builder
  tripStart: '',
};

const listeners = new Set();
export const subscribe = (fn) => listeners.add(fn);
export const update = () => listeners.forEach((fn) => fn());

/* ---- URL and storage ----
   The query string is a complete serialisation of the view, so it doubles as
   the storage format: there is no second schema to keep in step. */
const URL_STR = ['q', 'board', 'direction', 'scope', 'sortKey', 'sortDir', 'tripStart'];
const URL_NUM = ['minLevel', 'maxLevel', 'minXp', 'maxXp', 'corridor', 'freeSlots'];
const URL_BOOL = ['hideUnknownXp', 'recoverAtOrigin', 'boardAtDest', 'showAllRoutes', 'mapOpen'];
const URL_SET = ['from', 'to', 'calls', 'region', 'ocean'];
const SEP = '~';   // port names hold spaces, commas and apostrophes; never this

/* Param names are part of the app's public surface: links get shared and
   bookmarked. Where a state key reads better than its original param, the
   original name wins. */
const PARAM = { mapOpen: 'map', showAllRoutes: 'allRoutes' };
const param = (key) => PARAM[key] || key;
const STORE_KEY = 'osrs-port-tasks:filters:v1';

/** A key's default, read off `state` before anything has touched it: written
    once, where the key itself is declared. */
export const DEFAULTS = Object.fromEntries(
  [...URL_STR, ...URL_NUM].map((k) => [k, state[k]]));

export function stateToUrl() {
  const p = new URLSearchParams();
  // only what differs from the default, so a shared link carries no noise
  for (const k of [...URL_STR, ...URL_NUM]) {
    if (state[k] !== DEFAULTS[k] && state[k] !== null) p.set(param(k), state[k]);
  }
  for (const k of URL_BOOL) if (state[k]) p.set(param(k), '1');
  for (const k of URL_SET) if (state[k].size) p.set(param(k), [...state[k]].join(SEP));
  if (state.trip.length) p.set('trip', state.trip.join(SEP));

  const qs = p.toString();
  history.replaceState(null, '', qs ? '?' + qs : location.pathname);
  store(STORE_KEY, qs);
}

export function urlToState() {
  const p = new URLSearchParams(location.search);
  for (const k of URL_STR) if (p.has(param(k))) state[k] = p.get(param(k));
  // an absent param reads null and an empty one '', and neither is a number
  for (const k of URL_NUM) if (p.get(param(k))) state[k] = Number(p.get(param(k)));
  for (const k of URL_BOOL) state[k] = p.get(param(k)) === '1';
  for (const k of URL_SET) {
    // Mutate rather than reassign: multi-selects close over these Sets, so a
    // fresh object would silently orphan the dropdown from state.
    const values = p.has(param(k)) ? p.get(param(k)).split(SEP).filter(Boolean) : [];
    state[k].clear();
    for (const v of values) state[k].add(v);
  }
  state.trip = p.has('trip')
    ? p.get('trip').split(SEP).map(Number).filter((id) => TASK_BY_ID.has(id))
    : [];
}

/** An explicit link wins; a bare URL falls back to this browser's last view. */
export function restoreFromStorageIfBare() {
  if (location.search) return;
  const saved = stored(STORE_KEY);
  if (saved) history.replaceState(null, '', '?' + saved);
}

export function resetState() {
  Object.assign(state, DEFAULTS, {
    hideUnknownXp: false, recoverAtOrigin: false, boardAtDest: false,
    showAllRoutes: false, trip: [],
  });
  for (const k of URL_SET) state[k].clear();
}
