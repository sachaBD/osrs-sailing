/* Bootstrap and event wiring. The only module that knows about all the others. */
import { $, $$ } from './dom.js';
import { TASKS, allPorts, allRegions, allOceans, MAP_META } from './ports.js';
import {
  state, subscribe, update, stateToUrl, urlToState,
  restoreFromStorageIfBare, resetState, DEFAULTS,
} from './state.js';
import { filtered, sorted } from './filters.js';
import { multiSelect, closeMenusOnOutsideClick } from './multiselect.js';
import { renderTable, exportCsv } from './table.js';
import { renderTripPanel, toggleTripTask, currentTrip, portsNearRoute } from './trip.js';
import { boardValues, renderBoardPanel } from './boards.js';
import { initViewer, fit, zoomAt, restoreViewOrFit, applyTransform, view } from './map/viewer.js';
import { drawOverlay } from './map/overlay.js';

let viewer = null;
let visibleRows = [];

function render() {
  visibleRows = sorted(filtered());
  stateToUrl();
  renderTable(visibleRows);
  $('#filters-toggle').textContent = visibleRows.length === TASKS.length
    ? 'Filters' : `Filters · ${visibleRows.length} of ${TASKS.length}`;
  renderTripPanel();
  // valued once, drawn twice: the panel ranks the boards and the map marks them
  const boards = boardValues(visibleRows);
  renderBoardPanel(boards);
  if (view.ready) drawOverlay(viewer.svg, visibleRows, boards);
}

/* A control that edits one state key says which in the markup, and these two
   read that same declaration. Wiring and syncing used to be two hand-kept
   lists of the same fourteen facts, which is precisely how a control ships
   dead: bound but never synced, or synced but never bound. */

const controls = () => $$('[data-state]');

function bindControls() {
  for (const el of controls()) {
    const key = el.dataset.state;
    // a typo in the markup would otherwise quietly invent a state key
    if (!(key in state)) throw new Error(`${el.id}: no state key "${key}"`);
    el.addEventListener('input', () => {
      state[key] = el.type === 'checkbox' ? el.checked
        : el.type === 'number' ? (el.value === '' ? DEFAULTS[key] : Number(el.value))
        : el.value;
      update();
    });
  }
}

/** Push state into the controls, for links and restored sessions. */
function syncControls() {
  for (const el of controls()) {
    const value = state[el.dataset.state];
    if (el.type === 'checkbox') el.checked = value;
    // a control with a placeholder shows nothing at its default: the
    // placeholder is already saying what that default is
    else el.value = value === null || (el.placeholder && value === DEFAULTS[el.dataset.state])
      ? '' : value;
  }
  $$('.ms').forEach((ms) => ms._multi.apply());
}

function fillSelect(selector, values, placeholder) {
  $(selector).innerHTML = `<option value="">${placeholder}</option>` +
    values.map((v) => `<option value="${v}">${v}</option>`).join('');
}

function wireFilters() {
  fillSelect('#f-board', allPorts, 'Any notice board');
  multiSelect('#f-from', allPorts, 'Any origin', state.from, update);
  multiSelect('#f-to', allPorts, 'Any destination', state.to, update);
  multiSelect('#f-calls', allPorts, 'Any port', state.calls, update);
  multiSelect('#f-region', allRegions, 'Any region', state.region, update);
  multiSelect('#f-ocean', allOceans, 'Any ocean', state.ocean, update);
  closeMenusOnOutsideClick();
  bindControls();

  $$('th[data-key]').forEach((th) => {
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (state.sortKey === key) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else { state.sortKey = key; state.sortDir = th.dataset.default || 'desc'; }
      update();
    });
  });

  // On a phone the filter bar is a screenful of its own, which puts the map
  // and the table below the fold before you have done anything. Fold it away
  // there, and say on the button when something is filtering, so a folded bar
  // cannot quietly hide why the table looks short.
  const narrow = window.matchMedia('(max-width: 760px)');
  const fold = (on) => {
    $('#filters').classList.toggle('folded', on);
    $('#filters-toggle').setAttribute('aria-expanded', String(!on));
  };
  fold(narrow.matches);
  narrow.addEventListener('change', (e) => fold(e.matches));
  $('#filters-toggle').addEventListener('click',
    () => fold(!$('#filters').classList.contains('folded')));

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
  // the "sailing past" chips filter to tasks with that port at either end,
  // which is the question the panel raises: I am going by, is there work to
  // load or drop off there? Mutate the Set: the dropdown holds it by reference
  $('#trip-passing').addEventListener('click', (e) => {
    const chip = e.target.closest('[data-port]');
    if (!chip) return;
    const port = chip.dataset.port;
    if (!state.calls.delete(port)) state.calls.add(port);
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
