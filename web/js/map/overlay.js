/* Markers and routes drawn over the map tiles. */
import { esc } from '../dom.js';
import { state } from '../state.js';
import { LOCATIONS, MAP_META, regionOf, dockLevelOf, hasBoardAt } from '../ports.js';
import { currentTrip, portsNearRoute } from '../trip.js';
import { courseBetween, courseThrough } from '../course.js';
import { layerXY, toLayer } from './viewer.js';

/** Above this many rows the every-route view is an unreadable hairball. */
const ROUTE_LIMIT = 120;

/** Game coordinates -> an SVG points list in layer space. */
const polyline = (points) => points.map((p) => toLayer(p[0], p[1]).join(',')).join(' ');

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
    const course = courseBetween(route.from, route.to);
    if (!course.length) continue;
    const label = `${route.from} to ${route.to}: ${route.n} task${route.n === 1 ? '' : 's'}`;
    parts.push(`<polyline class="route" points="${polyline(course)}"` +
      ` stroke-width="${1.5 + 3 * (route.n / busiest)}"><title>${esc(label)}</title></polyline>`);
  }
  return parts;
}

/** The sailed course through every stop, twice: a dark casing for legibility,
    then the coloured line on top of it. One path, so the casing never shows
    through at the joins between legs. */
function tripLines(stops) {
  const course = courseThrough(stops.map((s) => s.port));
  if (course.length < 2) return [];
  const points = polyline(course);
  return [`<polyline class="trip-casing" points="${points}"></polyline>`,
          `<polyline class="trip-leg" points="${points}"></polyline>`];
}

function markerHtml(name, { stopNums, near, touched, hasTrip, worth, mostWorth }) {
  const point = layerXY(name);
  if (!point) return '';

  const classes = ['marker'];
  if (worth > 0) classes.push('worth-a-stop');
  // only a port with a notice board has tasks to filter to, so only those click
  if (hasBoardAt(name)) classes.push('boardable');
  if (state.board === name) classes.push('board-filtered');
  if (stopNums.length) classes.push('on-trip');
  else if (near) classes.push('near-route');
  else if (hasTrip || !touched) classes.push('dim');
  // labels only where they earn their place, or 30 names collide
  if (stopNums.length || near) classes.push('labelled');

  // A halo the size of what the board is worth stopping at. Area, not radius,
  // carries the value: the eye reads area, and the spread across boards is
  // wide enough that a linear radius would bury everything below the best.
  const halo = worth > 0
    ? `<circle class="worth" r="${(9 + 22 * Math.sqrt(worth / mostWorth)).toFixed(1)}"></circle>`
    : '';

  const badge = stopNums.length
    ? `<g class="stop-badge"><circle r="${stopNums.length > 1 ? 15 : 11}"></circle>` +
      `<text class="stop-n" y="4">${stopNums.join(',')}</text></g>`
    : '';

  const level = dockLevelOf(name);
  const tip = `${name} - ${regionOf(name)}${level ? `, dock level ${level}` : ''}` +
    (near ? `\nsailing past: ${near.dist} tiles off leg ${near.leg}` : '') +
    (hasBoardAt(name)
      ? `\nclick to ${state.board === name ? 'clear the' : 'see its'} notice board`
      : '\nno notice board') +
    (worth > 0 ? `\nan average draw off this board is worth ${Math.round(worth).toLocaleString()} xp` : '');

  return `<g class="${classes.join(' ')}" data-port="${esc(name)}"` +
    ` transform="translate(${point[0]},${point[1]})">` +
    `${halo}<circle class="hit" r="16"></circle><circle class="dot" r="7"></circle>` +
    `${badge}<text class="label" y="-14">${esc(name)}</text>` +
    `<title>${esc(tip)}</title></g>`;
}

/** Draw the planned trip if there is one, otherwise the filtered routes. */
export function drawOverlay(svg, rows, boards = []) {
  const [w, h] = MAP_META.size;
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.style.width = `${w}px`;
  svg.style.height = `${h}px`;

  const trip = currentTrip();
  const nearRoute = portsNearRoute(trip.stops);
  const hasTrip = trip.stops.length > 0;

  const worth = new Map(boards.map((b) => [b.port, b.value]));
  const mostWorth = Math.max(1, ...worth.values());

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
      worth: worth.get(name) || 0, mostWorth,
    }));
  }
  svg.innerHTML = parts.join('');
}
