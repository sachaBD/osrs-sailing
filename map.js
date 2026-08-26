/* Hand-rolled pan/zoom tile map. Layer coordinates are game tiles: a point at
   game (x, y) sits at (x - originX, originY - y) inside #map-layer, and a CSS
   transform handles pan and zoom. Game y grows north but screen y grows down,
   hence the flip. */
const MAP = window.PORT_MAP;

const view = {
  scale: 0.55,      // screen px per game tile
  x: 0, y: 0,       // pan, in screen px
  tileZoom: 0,
  ready: false,
};

const VIEW_KEY = 'osrs-port-tasks:view:v1';   // pan/zoom, persisted per browser

const MIN_SCALE = 0.3;
const MAX_SCALE = 3;
const FINE_TILES_ABOVE = 1.1;   // switch to zoom-1 tiles past this scale

const el = {};
const toLayer = (x, y) => [x - MAP.origin[0], MAP.origin[1] - y];

function coordsOf(loc) {
  const c = (LOCATIONS[loc] || {}).coords;
  if (!c) return null;
  const [x, y] = c.split(',').map(Number);
  return toLayer(x, y);
}

const tileUrl = (tmpl, z, x, y) =>
  tmpl.replace('{z}', z).replace('{x}', x).replace('{y}', y);

/* Rebuild the tile grid for the current tile zoom. */
function drawTiles() {
  const z = view.tileZoom;
  const grid = MAP.zooms[String(z)];
  if (!grid) return;
  const span = grid.span;
  const frag = document.createDocumentFragment();

  for (let tx = grid.tx[0]; tx <= grid.tx[1]; tx++) {
    for (let ty = grid.ty[0]; ty <= grid.ty[1]; ty++) {
      const img = document.createElement('img');
      img.className = 'map-tile';
      img.src = tileUrl(MAP.localUrl, z, tx, ty);
      img.draggable = false;
      // fall back to the wiki if this tile is not in tiles/ yet (`make tiles`)
      img.onerror = () => {
        if (img.dataset.fellBack) { img.style.visibility = 'hidden'; return; }
        img.dataset.fellBack = '1';
        img.src = tileUrl(MAP.remoteUrl, z, tx, ty);
      };
      const [lx, ly] = toLayer(tx * span, (ty + 1) * span);
      Object.assign(img.style, {
        left: lx + 'px', top: ly + 'px', width: span + 'px', height: span + 'px',
      });
      frag.appendChild(img);
    }
  }
  el.tiles.replaceChildren(frag);
}

/* Overlay: the planned trip if there is one, otherwise the filtered routes. */
function drawOverlay(rows) {
  const [w, h] = MAP.size;
  el.svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
  el.svg.style.width = w + 'px';
  el.svg.style.height = h + 'px';

  const trip = currentTrip();
  const onTrip = new Set(trip.stops.map((s) => s.port));
  const nearRoute = portsNearRoute(trip.stops);
  const parts = [];

  // Background routes are a hairball at full dataset size, so they are opt-in
  // once a trip exists or the filtered set is large.
  const showRoutes = state.showAllRoutes || (!trip.stops.length && rows.length <= 120);
  const touched = new Set();
  for (const t of rows) { touched.add(t.from); touched.add(t.to); touched.add(t.noticeBoard); }

  if (showRoutes) {
    const routes = new Map();
    for (const t of rows) {
      if (t.from === t.to) continue;
      const key = t.from + '>' + t.to;
      const r = routes.get(key) || { from: t.from, to: t.to, n: 0 };
      r.n += 1;
      routes.set(key, r);
    }
    const maxN = Math.max(1, ...[...routes.values()].map((r) => r.n));
    for (const r of routes.values()) {
      const a = coordsOf(r.from);
      const b = coordsOf(r.to);
      if (!a || !b) continue;
      parts.push(
        '<line class="route" x1="' + a[0] + '" y1="' + a[1] + '" x2="' + b[0] + '" y2="' + b[1] +
        '" stroke-width="' + (1.5 + 3 * (r.n / maxN)) + '"><title>' + r.from + ' to ' + r.to +
        ': ' + r.n + ' task' + (r.n === 1 ? '' : 's') + '</title></line>');
    }
  }

  // The planned route. Each leg is drawn twice: a dark casing underneath so the
  // line stays readable over the map's clutter, then the coloured line on top.
  for (let i = 1; i < trip.stops.length; i++) {
    const a = coordsOf(trip.stops[i - 1].port);
    const b = coordsOf(trip.stops[i].port);
    if (!a || !b) continue;
    const coords = ' x1="' + a[0] + '" y1="' + a[1] + '" x2="' + b[0] + '" y2="' + b[1] + '"';
    parts.push('<line class="trip-casing"' + coords + '></line>');
    parts.push('<line class="trip-leg"' + coords + '></line>');
  }

  for (const [name, meta] of Object.entries(LOCATIONS)) {
    const p = coordsOf(name);
    if (!p) continue;
    // a port can be visited more than once, so badge every stop number it holds
    const stopNums = trip.stops
      .map((s, i) => (s.port === name ? i + 1 : 0)).filter(Boolean);
    const cls = ['marker'];
    // with a trip on screen every other port is background, filtered or not
    const near = nearRoute.get(name);
    if (onTrip.has(name)) cls.push('on-trip');
    else if (near) cls.push('near-route');
    else if (trip.stops.length || !touched.has(name)) cls.push('dim');
    if (state.port.has(name)) cls.push('picked');
    // labels only where they earn their place, else 30 names collide
    if (onTrip.has(name) || near || state.port.has(name)) cls.push('labelled');

    const badge = stopNums.length
      ? '<g class="stop-badge"><circle r="' + (stopNums.length > 1 ? 15 : 11) + '"></circle>' +
        '<text class="stop-n" y="4">' + stopNums.join(',') + '</text></g>'
      : '';
    parts.push(
      '<g class="' + cls.join(' ') + '" data-port="' + name + '" transform="translate(' +
      p[0] + ',' + p[1] + ')">' +
      '<circle class="hit" r="16"></circle>' +
      '<circle class="dot" r="7"></circle>' + badge +
      '<text class="label" y="-14">' + name + '</text>' +
      '<title>' + name + ' - ' + meta.region +
      (meta.dock_level ? ', dock level ' + meta.dock_level : '') +
      (near ? '\nsailing past: ' + near.dist + ' tiles off leg ' + near.leg : '') +
      '</title></g>');
  }
  el.svg.innerHTML = parts.join('');
}

/* Keep some of the map on screen: without this you can fling it into the void
   and the only way back is the Fit button. */
function clampPan() {
  const box = el.viewport.getBoundingClientRect();
  if (!box.width) return;
  const w = MAP.size[0] * view.scale;
  const h = MAP.size[1] * view.scale;
  const keep = Math.min(140, w / 2, h / 2);   // minimum map visible on any edge
  view.x = Math.min(box.width - keep, Math.max(keep - w, view.x));
  view.y = Math.min(box.height - keep, Math.max(keep - h, view.y));
}

function applyTransform() {
  clampPan();
  el.layer.style.transform =
    'translate(' + view.x + 'px,' + view.y + 'px) scale(' + view.scale + ')';
  // keep markers and labels a constant size on screen
  el.layer.style.setProperty('--inv', 1 / view.scale);
  el.zoomLabel.textContent = Math.round(view.scale * 100) + '%';

  const want = (view.scale > FINE_TILES_ABOVE && MAP.zooms['1']) ? 1 : 0;
  if (want !== view.tileZoom) {
    view.tileZoom = want;
    drawTiles();
  }
  saveView();
}

let viewSaveTimer = null;
function saveView() {
  clearTimeout(viewSaveTimer);
  viewSaveTimer = setTimeout(() => {
    store(VIEW_KEY, JSON.stringify({ scale: view.scale, x: view.x, y: view.y }));
  }, 250);
}

/* Restore a previous pan/zoom, or fall back to fitting all ports. */
function restoreViewOrFit() {
  const saved = stored(VIEW_KEY);
  if (saved) {
    try {
      const v = JSON.parse(saved);
      if (Number.isFinite(v.scale) && Number.isFinite(v.x) && Number.isFinite(v.y)) {
        view.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale));
        view.x = v.x;
        view.y = v.y;
        applyTransform();
        return;
      }
    } catch (_) { /* corrupt entry: fit instead */ }
  }
  fit();
}

function zoomAt(factor, cx, cy) {
  const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
  const k = next / view.scale;
  // keep the point under the cursor fixed
  view.x = cx - (cx - view.x) * k;
  view.y = cy - (cy - view.y) * k;
  view.scale = next;
  applyTransform();
}

function fit() {
  const box = el.viewport.getBoundingClientRect();
  const pts = Object.keys(LOCATIONS).map(coordsOf).filter(Boolean);
  if (!pts.length || !box.width) return;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = 70;
  view.scale = Math.min(
    (box.width - pad * 2) / Math.max(1, maxX - minX),
    (box.height - pad * 2) / Math.max(1, maxY - minY));
  view.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale));
  view.x = box.width / 2 - ((minX + maxX) / 2) * view.scale;
  view.y = box.height / 2 - ((minY + maxY) / 2) * view.scale;
  applyTransform();
}

function initMap() {
  el.panel = document.querySelector('#map-panel');
  el.viewport = document.querySelector('#map-viewport');
  el.layer = document.querySelector('#map-layer');
  el.tiles = document.querySelector('#map-tiles');
  el.svg = document.querySelector('#map-overlay');
  el.zoomLabel = document.querySelector('#map-zoom-label');
  el.toggle = document.querySelector('#map-toggle');

  drawTiles();

  let dragging = false, moved = false, lastX = 0, lastY = 0, startX = 0, startY = 0;
  el.viewport.addEventListener('pointerdown', (e) => {
    dragging = true;
    moved = false;
    lastX = startX = e.clientX;
    lastY = startY = e.clientY;
    // Capture is deliberately NOT taken here: while a pointer is captured the
    // browser retargets the click to the capturing element, which would stop
    // marker clicks ever reaching the overlay. It is taken once a drag starts.
  });
  el.viewport.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    if (!moved && Math.hypot(e.clientX - startX, e.clientY - startY) > 3) {
      moved = true;
      el.viewport.setPointerCapture(e.pointerId);
    }
    if (moved) {
      view.x += e.clientX - lastX;
      view.y += e.clientY - lastY;
      applyTransform();
    }
    lastX = e.clientX;
    lastY = e.clientY;
  });
  const endDrag = (e) => {
    dragging = false;
    if (el.viewport.hasPointerCapture && el.viewport.hasPointerCapture(e.pointerId)) {
      el.viewport.releasePointerCapture(e.pointerId);
    }
  };
  el.viewport.addEventListener('pointerup', endDrag);
  el.viewport.addEventListener('pointercancel', endDrag);

  // A press-and-drag would otherwise start a text selection or a native image
  // drag, which hijacks panning. Cancelling those two events leaves the
  // compatibility mouse events (and so marker clicks) untouched, which
  // preventDefault on pointerdown would not.
  el.viewport.addEventListener('dragstart', (e) => e.preventDefault());
  el.viewport.addEventListener('selectstart', (e) => e.preventDefault());

  el.viewport.addEventListener('wheel', (e) => {
    e.preventDefault();
    const box = el.viewport.getBoundingClientRect();
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - box.left, e.clientY - box.top);
  }, { passive: false });

  // click a port to filter the table by it, click again to clear it
  el.svg.addEventListener('click', (e) => {
    if (moved) return;
    const g = e.target.closest('.marker');
    if (!g) return;
    const name = g.dataset.port;
    if (state.port.has(name)) state.port.delete(name); else state.port.add(name);
    render();
  });

  const btnZoom = (factor) => () => {
    const b = el.viewport.getBoundingClientRect();
    zoomAt(factor, b.width / 2, b.height / 2);
  };
  document.querySelector('#map-in').addEventListener('click', btnZoom(1.3));
  document.querySelector('#map-out').addEventListener('click', btnZoom(1 / 1.3));
  document.querySelector('#map-fit').addEventListener('click', fit);
  document.querySelector('#map-clear').addEventListener('click', () => {
    state.port.clear();
    render();
  });

  el.toggle.addEventListener('click', () => {
    const showing = !el.panel.hasAttribute('hidden');
    el.panel.toggleAttribute('hidden', showing);
    el.toggle.textContent = showing ? 'Show map' : 'Hide map';
    state.mapOpen = !showing;   // serialised into the URL like every other filter
    stateToUrl();
    if (!showing) {
      // first reveal: the viewport finally has a size to fit against
      if (!view.ready) { view.ready = true; restoreViewOrFit(); } else { applyTransform(); }
      drawOverlay(lastRows);
    }
  });

  window.addEventListener('resize', () => { if (view.ready) applyTransform(); });
}
