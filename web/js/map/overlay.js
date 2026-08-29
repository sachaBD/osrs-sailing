/* Markers and routes drawn over the map tiles. */
import { esc } from '../dom.js';
import { state } from '../state.js';
import { LOCATIONS, MAP_META, regionOf, dockLevelOf } from '../ports.js';
import { currentTrip, portsNearRoute } from '../trip.js';
import { layerXY } from './viewer.js';

/** Above this many rows the every-route view is an unreadable hairball. */
const ROUTE_LIMIT = 120;

function routeLines(rows) {
  const routes = new Map();
  for (const t of rows) {
    if (t.from === t.to) continue;
    const key = `${t.from}>${t.to}`;
    const route = routes.get(key) || { from: t.from, to: t.to, n: 0 };
    route.n += 1;
    routes.set(key, route);
  }

  const busiest = Math.max(1, ...[...routes.values()].map((r) => r.n));
  const parts = [];
  for (const route of routes.values()) {
    const a = layerXY(route.from);
    const b = layerXY(route.to);
    if (!a || !b) continue;
    const label = `${route.from} to ${route.to}: ${route.n} task${route.n === 1 ? '' : 's'}`;
    parts.push(`<line class="route" x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"` +
      ` stroke-width="${1.5 + 3 * (route.n / busiest)}"><title>${esc(label)}</title></line>`);
  }
  return parts;
}

/** Each leg twice: a dark casing for legibility, then the coloured line. */
function tripLines(stops) {
  const parts = [];
  for (let i = 1; i < stops.length; i++) {
    const a = layerXY(stops[i - 1].port);
    const b = layerXY(stops[i].port);
    if (!a || !b) continue;
    const coords = ` x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"`;
    parts.push(`<line class="trip-casing"${coords}></line>`);
    parts.push(`<line class="trip-leg"${coords}></line>`);
  }
  return parts;
}

function markerHtml(name, { stopNums, near, touched, hasTrip }) {
  const point = layerXY(name);
  if (!point) return '';

  const classes = ['marker'];
  if (stopNums.length) classes.push('on-trip');
  else if (near) classes.push('near-route');
  else if (hasTrip || !touched) classes.push('dim');
  if (state.port.has(name)) classes.push('picked');
  // labels only where they earn their place, or 30 names collide
  if (stopNums.length || near || state.port.has(name)) classes.push('labelled');

  const badge = stopNums.length
    ? `<g class="stop-badge"><circle r="${stopNums.length > 1 ? 15 : 11}"></circle>` +
      `<text class="stop-n" y="4">${stopNums.join(',')}</text></g>`
    : '';

  const level = dockLevelOf(name);
  const tip = `${name} - ${regionOf(name)}${level ? `, dock level ${level}` : ''}` +
    (near ? `\nsailing past: ${near.dist} tiles off leg ${near.leg}` : '');

  return `<g class="${classes.join(' ')}" data-port="${esc(name)}"` +
    ` transform="translate(${point[0]},${point[1]})">` +
    '<circle class="hit" r="16"></circle><circle class="dot" r="7"></circle>' +
    `${badge}<text class="label" y="-14">${esc(name)}</text>` +
    `<title>${esc(tip)}</title></g>`;
}

/** Draw the planned trip if there is one, otherwise the filtered routes. */
export function drawOverlay(svg, rows) {
  const [w, h] = MAP_META.size;
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.style.width = `${w}px`;
  svg.style.height = `${h}px`;

  const trip = currentTrip();
  const nearRoute = portsNearRoute(trip.stops);
  const hasTrip = trip.stops.length > 0;

  const touched = new Set();
  for (const t of rows) { touched.add(t.from); touched.add(t.to); touched.add(t.noticeBoard); }

  const showRoutes = state.showAllRoutes || (!hasTrip && rows.length <= ROUTE_LIMIT);
  const parts = showRoutes ? routeLines(rows) : [];
  parts.push(...tripLines(trip.stops));

  for (const name of Object.keys(LOCATIONS)) {
    // a port can be visited more than once, so badge every stop number it holds
    const stopNums = trip.stops
      .map((s, i) => (s.port === name ? i + 1 : 0)).filter(Boolean);
    parts.push(markerHtml(name, {
      stopNums, near: nearRoute.get(name), touched: touched.has(name), hasTrip,
    }));
  }
  svg.innerHTML = parts.join('');
}
