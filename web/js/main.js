/* Bootstrap and event wiring. The only module that knows about all the others. */
import { $, $$ } from './dom.js';
import { allPorts, allRegions, allOceans, MAP_META } from './ports.js';
import {
  state, subscribe, update, stateToUrl, urlToState,
  restoreFromStorageIfBare, resetState, DEFAULTS,
} from './state.js';
import { filtered, sorted } from './filters.js';
import { multiSelect, closeMenusOnOutsideClick } from './multiselect.js';
import { renderTable, exportCsv } from './table.js';
import { renderTripPanel, toggleTripTask, currentTrip, portsNearRoute } from './trip.js';
import { initViewer, fit, zoomAt, restoreViewOrFit, applyTransform, view } from './map/viewer.js';
import { drawOverlay } from './map/overlay.js';

let viewer = null;
let visibleRows = [];

function render() {
  visibleRows = sorted(filtered());
  stateToUrl();
  renderTable(visibleRows);
  renderTripPanel();
  if (view.ready) drawOverlay(viewer.svg, visibleRows);
}

/** Bind a control to a state key, re-rendering on change. */
function bind(selector, key, parse = (v) => v) {
  $(selector).addEventListener('input', (e) => {
    state[key] = parse(e.target.type === 'checkbox' ? e.target.checked : e.target.value);
    update();
  });
}

const numberOr = (fallback) => (v) => (v === '' ? fallback : Number(v));

function fillSelect(selector, values, placeholder) {
  $(selector).innerHTML = `<option value="">${placeholder}</option>` +
    values.map((v) => `<option value="${v}">${v}</option>`).join('');
}

/** Push state into the controls, for links and restored sessions. */
function syncControls() {
  const set = (selector, value) => { const el = $(selector); if (el) el.value = value; };
  set('#f-q', state.q);
  set('#f-board', state.board);
  set('#f-direction', state.direction);
  set('#f-scope', state.scope);
  set('#f-min', state.minLevel === DEFAULTS.minLevel ? '' : state.minLevel);
  set('#f-max', state.maxLevel === DEFAULTS.maxLevel ? '' : state.maxLevel);
  set('#f-xpmin', state.minXp === null ? '' : state.minXp);
  set('#f-xpmax', state.maxXp === null ? '' : state.maxXp);
  set('#trip-corridor', state.corridor);
  $('#f-unknown').checked = state.hideUnknownXp;
  $('#f-recover').checked = state.recoverAtOrigin;
  $('#f-board-dest').checked = state.boardAtDest;
  $('#f-all-routes').checked = state.showAllRoutes;
  $$('.ms').forEach((ms) => ms._multi.apply());
}

function wireFilters() {
  fillSelect('#f-board', allPorts, 'Any notice board');
  multiSelect('#f-from', allPorts, 'Any origin', state.from, update);
  multiSelect('#f-to', allPorts, 'Any destination', state.to, update);
  multiSelect('#f-region', allRegions, 'Any region', state.region, update);
  multiSelect('#f-ocean', allOceans, 'Any ocean', state.ocean, update);
  closeMenusOnOutsideClick();

  bind('#f-q', 'q');
  bind('#f-board', 'board');
  bind('#f-direction', 'direction');
  bind('#f-scope', 'scope');
  bind('#f-unknown', 'hideUnknownXp');
  bind('#f-recover', 'recoverAtOrigin');
  bind('#f-board-dest', 'boardAtDest');
  bind('#f-all-routes', 'showAllRoutes');
  bind('#f-min', 'minLevel', numberOr(DEFAULTS.minLevel));
  bind('#f-max', 'maxLevel', numberOr(DEFAULTS.maxLevel));
  bind('#f-xpmin', 'minXp', numberOr(null));
  bind('#f-xpmax', 'maxXp', numberOr(null));
  bind('#trip-corridor', 'corridor', numberOr(DEFAULTS.corridor));

  $$('th[data-key]').forEach((th) => {
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (state.sortKey === key) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else { state.sortKey = key; state.sortDir = th.dataset.default || 'desc'; }
      update();
    });
  });

  $('#reset').addEventListener('click', () => {
    resetState();
    syncControls();
    update();
  });
  $('#export').addEventListener('click', () => exportCsv(visibleRows));
}

function wireTrip() {
  // delegated, so it survives every table re-render
  $('#tbody').addEventListener('click', (e) => {
    const button = e.target.closest('.trip-btn');
    if (!button) return;
    toggleTripTask(Number(button.dataset.id));
    update();
  });
  // the "sailing past" chips filter to that port's notice board, which is the
  // question the panel raises: I am going by, is there work there?
  $('#trip-passing').addEventListener('click', (e) => {
    const chip = e.target.closest('[data-board]');
    if (!chip) return;
    state.board = state.board === chip.dataset.board ? '' : chip.dataset.board;
    syncControls();
    update();
  });
  $('#trip-clear').addEventListener('click', () => {
    state.trip = [];
    state.tripStart = '';
    update();
  });
  $('#trip-start').addEventListener('change', (e) => {
    state.tripStart = e.target.value;
    update();
  });
}

function wireMap() {
  viewer = initViewer({
    onPortClick(name) {
      state.board = state.board === name ? '' : name;
      syncControls();
      update();
    },
  });

  const zoomFromCentre = (factor) => () => {
    const box = $('#map-viewport').getBoundingClientRect();
    zoomAt(factor, box.width / 2, box.height / 2);
  };
  $('#map-in').addEventListener('click', zoomFromCentre(1.3));
  $('#map-out').addEventListener('click', zoomFromCentre(1 / 1.3));
  $('#map-fit').addEventListener('click', () => fit(allPorts));
  $('#map-toggle').addEventListener('click', () => {
    const showing = viewer.isOpen();
    viewer.setOpen(!showing);
    $('#map-toggle').textContent = showing ? 'Show map' : 'Hide map';
    state.mapOpen = !showing;
    if (!showing) {
      // first reveal: the viewport finally has a size to fit against
      if (!view.ready) { view.ready = true; restoreViewOrFit(allPorts); } else applyTransform();
      drawOverlay(viewer.svg, visibleRows);
    }
    update();
  });

  window.addEventListener('resize', () => { if (view.ready) applyTransform(); });
}

restoreFromStorageIfBare();
urlToState();
wireFilters();
wireTrip();
wireMap();
syncControls();
subscribe(render);
if (state.mapOpen) $('#map-toggle').click();
render();

/* A single, explicit handle for the smoke test. Modules export nothing to the
   page otherwise, so this is the only thing tests may depend on. */
window.__app = { state, view, render, MAP_META, currentTrip, portsNearRoute };
