/* Pan/zoom tile viewer, hand-rolled so the app keeps zero runtime dependencies.

   Layer coordinates are game tiles: a point at game (x, y) sits at
   (x - originX, originY - y) inside #map-layer, and a CSS transform handles pan
   and zoom. Game y grows north but screen y grows down, hence the flip. */
import { $, store, stored } from '../dom.js';
import { MAP_META, portXY } from '../ports.js';

const VIEW_KEY = 'osrs-port-tasks:view:v1';
const MIN_SCALE = 0.3;
const MAX_SCALE = 3;
const FINE_TILES_ABOVE = 1.1;   // switch to zoom-1 tiles past this scale
const MIN_VISIBLE = 140;        // px of map kept on screen when panning

export const view = { scale: 0.55, x: 0, y: 0, tileZoom: 0, ready: false };

const el = {};

/** Game coordinates to layer coordinates. */
export const toLayer = (x, y) => [x - MAP_META.origin[0], MAP_META.origin[1] - y];

/** A port's position in layer coordinates, or null if it has none. */
export function layerXY(name) {
  const p = portXY(name);
  return p ? toLayer(p[0], p[1]) : null;
}

const tileUrl = (template, z, x, y) =>
  template.replace('{z}', z).replace('{x}', x).replace('{y}', y);

function drawTiles() {
  const grid = MAP_META.zooms[String(view.tileZoom)];
  if (!grid) return;
  const span = grid.span;
  const frag = document.createDocumentFragment();

  for (let tx = grid.tx[0]; tx <= grid.tx[1]; tx++) {
    for (let ty = grid.ty[0]; ty <= grid.ty[1]; ty++) {
      const img = document.createElement('img');
      img.className = 'map-tile';
      img.src = tileUrl(MAP_META.localUrl, view.tileZoom, tx, ty);
      img.draggable = false;
      // fall back to the wiki when a tile is not in tiles/ yet (`make tiles`)
      img.onerror = () => {
        if (img.dataset.fellBack) { img.style.visibility = 'hidden'; return; }
        img.dataset.fellBack = '1';
        img.src = tileUrl(MAP_META.remoteUrl, view.tileZoom, tx, ty);
      };
      const [left, top] = toLayer(tx * span, (ty + 1) * span);
      Object.assign(img.style,
        { left: `${left}px`, top: `${top}px`, width: `${span}px`, height: `${span}px` });
      frag.appendChild(img);
    }
  }
  el.tiles.replaceChildren(frag);
}

/** Keep some map on screen; otherwise it can be flung out of reach. */
function clampPan() {
  const box = el.viewport.getBoundingClientRect();
  if (!box.width) return;
  const w = MAP_META.size[0] * view.scale;
  const h = MAP_META.size[1] * view.scale;
  const keep = Math.min(MIN_VISIBLE, w / 2, h / 2);
  view.x = Math.min(box.width - keep, Math.max(keep - w, view.x));
  view.y = Math.min(box.height - keep, Math.max(keep - h, view.y));
}

let saveTimer = null;
function saveView() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    store(VIEW_KEY, JSON.stringify({ scale: view.scale, x: view.x, y: view.y }));
  }, 250);
}

export function applyTransform() {
  clampPan();
  el.layer.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  // markers and labels counter-scale so they stay a constant size on screen
  el.layer.style.setProperty('--inv', 1 / view.scale);
  el.zoomLabel.textContent = `${Math.round(view.scale * 100)}%`;

  const wanted = (view.scale > FINE_TILES_ABOVE && MAP_META.zooms['1']) ? 1 : 0;
  if (wanted !== view.tileZoom) {
    view.tileZoom = wanted;
    drawTiles();
  }
  saveView();
}

export function zoomAt(factor, cx, cy) {
  const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
  const ratio = next / view.scale;
  // keep whatever is under the cursor fixed
  view.x = cx - (cx - view.x) * ratio;
  view.y = cy - (cy - view.y) * ratio;
  view.scale = next;
  applyTransform();
}

export function fit(ports) {
  const box = el.viewport.getBoundingClientRect();
  const points = ports.map(layerXY).filter(Boolean);
  if (!points.length || !box.width) return;

  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const [minX, maxX] = [Math.min(...xs), Math.max(...xs)];
  const [minY, maxY] = [Math.min(...ys), Math.max(...ys)];
  const pad = 70;

  view.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.min(
    (box.width - pad * 2) / Math.max(1, maxX - minX),
    (box.height - pad * 2) / Math.max(1, maxY - minY))));
  view.x = box.width / 2 - ((minX + maxX) / 2) * view.scale;
  view.y = box.height / 2 - ((minY + maxY) / 2) * view.scale;
  applyTransform();
}

export function restoreViewOrFit(ports) {
  const saved = stored(VIEW_KEY);
  if (saved) {
    try {
      const v = JSON.parse(saved);
      if ([v.scale, v.x, v.y].every(Number.isFinite)) {
        view.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale));
        view.x = v.x;
        view.y = v.y;
        applyTransform();
        return;
      }
    } catch (_) { /* corrupt entry: fall through and fit */ }
  }
  fit(ports);
}

/** Wire up pan, zoom and marker clicks. `onPortClick` gets the port name; the
    overlay decides which markers are worth clicking. */
export function initViewer({ onPortClick }) {
  Object.assign(el, {
    panel: $('#map-panel'),
    viewport: $('#map-viewport'),
    layer: $('#map-layer'),
    tiles: $('#map-tiles'),
    svg: $('#map-overlay'),
    zoomLabel: $('#map-zoom-label'),
  });
  drawTiles();

  let dragging = false, moved = false, lastX = 0, lastY = 0, startX = 0, startY = 0;

  el.viewport.addEventListener('pointerdown', (e) => {
    dragging = true;
    moved = false;
    lastX = startX = e.clientX;
    lastY = startY = e.clientY;
    // Capture is deliberately not taken here: while a pointer is captured the
    // browser retargets the click to the capturing element, which would stop
    // marker clicks ever arriving. It is taken once a drag actually starts.
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
    if (el.viewport.hasPointerCapture?.(e.pointerId)) {
      el.viewport.releasePointerCapture(e.pointerId);
    }
  };
  el.viewport.addEventListener('pointerup', endDrag);
  el.viewport.addEventListener('pointercancel', endDrag);

  // A press-and-drag would otherwise start a text selection or a native image
  // drag, either of which hijacks panning. Cancelling these two leaves the
  // compatibility mouse events (and so clicks) alone, which preventDefault on
  // pointerdown would not.
  el.viewport.addEventListener('dragstart', (e) => e.preventDefault());
  el.viewport.addEventListener('selectstart', (e) => e.preventDefault());

  el.viewport.addEventListener('wheel', (e) => {
    e.preventDefault();
    const box = el.viewport.getBoundingClientRect();
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - box.left, e.clientY - box.top);
  }, { passive: false });

  el.svg.addEventListener('click', (e) => {
    if (moved) return;   // a drag that ended on a marker is not a click
    const marker = e.target.closest('.marker.boardable');
    if (marker) onPortClick(marker.dataset.port);
  });

  return {
    svg: el.svg,
    panel: el.panel,
    isOpen: () => !el.panel.hasAttribute('hidden'),
    setOpen(open) { el.panel.toggleAttribute('hidden', !open); },
  };
}
