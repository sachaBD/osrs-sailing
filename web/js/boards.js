/* What a notice board is worth stopping at.

   A board shows a handful of courier tasks drawn from its pool of about
   twenty, and you cannot see which until you are standing at it. So the value
   of the stop is an expectation over that draw: the best few of the offers you
   could actually use, each priced the way the trip prices everything else -
   XP less the time it costs, at the rate the trip is already running at.

   Two things make the arithmetic honest rather than hopeful:

   Offers you cannot use are not absent, they are dead. Inbound work, tasks
   outside your filters, tasks already in your hold: each still occupies one of
   the board's slots, so it crowds out a draw you wanted. A board of twenty
   tasks where six are usable is a much worse stop than a board of six.

   And the time a task costs is its insertion into *this* trip - the same
   measure the Δ XP/hr column shows - which already counts sailing out to the
   board and back. Nothing here needs a separate detour term; a board off your
   course prices itself out through the legs it would add.

   Two known conservatisms, both in the same direction. Each accepted task is
   costed as though it were inserted alone, so filling two slots at one board
   pays the sail out to it twice: with more than one free slot the value is a
   lower bound, and the further off course the board, the looser. And the
   insertion is measured against the trip as it stands, which is one step of
   lookahead - taking the work will change the route that prices the next
   stop. Both would need a joint insertion to fix, which is the travelling
   salesman we are deliberately not solving. */
import { $, esc } from './dom.js';
import { TASKS, hasBoardAt } from './ports.js';
import { COSTS } from './generated.js';
import { xpLift, currentTrip } from './trip.js';
import { legDistance, formatDuration, routeSeconds, round } from './cost.js';
import { state } from './state.js';

/** Every task a board can offer, whether or not it is on screen. */
export const POOLS = (() => {
  const pools = new Map();
  for (const t of TASKS) {
    if (!pools.has(t.noticeBoard)) pools.set(t.noticeBoard, []);
    pools.get(t.noticeBoard).push(t);
  }
  return pools;
})();

/* Pascal's triangle, big enough for the largest pool. Exact in doubles: the
   biggest number here is C(24,12), about 2.7 million. */
const CHOOSE = (() => {
  const size = Math.max(...[...POOLS.values()].map((p) => p.length)) + 2;
  const rows = [[1]];
  for (let n = 1; n < size; n++) {
    const prev = rows[n - 1];
    rows.push([1, ...prev.slice(1).map((v, i) => v + prev[i]), 1]);
  }
  return (n, k) => (k < 0 || k > n || n < 0 ? 0 : rows[n][k]);
})();

/** Expected total of the best `slots` values in a uniform draw of `offers`
    from `values`, without replacement.

    Exact, not sampled. Rank the pool best first; the task at rank i is drawn
    with probability offers/N, and survives into your hold when fewer than
    `slots` of the i tasks above it are drawn alongside it - a hypergeometric
    tail over the remaining N-1 slots. */
export function bestOfDraw(values, offers, slots) {
  const v = [...values].sort((a, b) => b - a);
  const N = v.length;
  const m = Math.min(offers, N);
  if (!N || !m || slots < 1) return 0;

  const ways = CHOOSE(N - 1, m - 1);
  let total = 0;
  for (let i = 0; i < N; i++) {
    if (v[i] <= 0) break;            // sorted, so nothing below here can help
    let kept = 0;
    for (let j = 0; j < slots && j <= i; j++) kept += CHOOSE(i, j) * CHOOSE(N - 1 - i, m - 1 - j);
    total += v[i] * (m / N) * (kept / ways);
  }
  return total;
}

/** What one offered task is worth to this trip, in XP, or 0 if it is no use.

    `rate` is the trip's own XP per second, so the time a task costs is priced
    at what those seconds would otherwise have earned. A task that cannot beat
    that is worth nothing rather than something negative: you would simply not
    accept it, and declining is free. */
function offerValue(task, rate, usable) {
  if (!usable.has(task.id)) return 0;
  const lift = xpLift(task);
  if (lift === null || lift.inTrip) return 0;
  const seconds = lift.seconds + COSTS.tBoard * COSTS.tick;
  return Math.max(0, lift.xp - rate * seconds);
}

/** Value every board against the current trip -> [{port, value, best, ...}].

    `rows` is what passes the filters: the tasks you would actually take, which
    is what separates a usable offer from a dead one. */
export function boardValues(rows) {
  if (!state.trip.length) return [];

  const trip = currentTrip();
  // XP per second: what a second of sailing is already earning, which is the
  // rate every offer has to beat before it is worth the time it costs
  const rate = trip.rate / 3600;
  const usable = new Set(rows.map((t) => t.id));
  const out = [];

  for (const [port, pool] of POOLS) {
    if (!hasBoardAt(port)) continue;    // a pool with no board is not a stop
    const values = pool.map((t) => offerValue(t, rate, usable));
    const live = values.filter((v) => v > 0).length;
    out.push({
      port,
      pool: pool.length,
      live,
      offers: COSTS.offers,
      // the expectation, and the luckiest draw it averages over
      value: bestOfDraw(values, COSTS.offers, state.freeSlots),
      best: Math.max(0, ...values),
      // context only: the value above already prices the sailing, but a rank
      // with no sense of what these stops cost is hard to read
      detour: detourFrom(trip.route, port),
    });
  }
  return out.sort((a, b) => b.value - a.value);
}

/** The sailing this stop would add to the trip, in seconds, or null when the
    port is uncharted from everywhere the trip goes.

    The extra water, not the distance to the nearest stop: those are different
    questions and only the first one is the one being asked. A port sitting
    halfway down a leg you already sail is hours from either end of it and
    costs you nothing to touch, which is exactly the case the old measure got
    wrong. So: the cheapest way to work the port into the route - slipped into
    any leg, or tacked on after the last stop, which is the whole sail out
    because the trip does not come back. */
export function detourFrom(route, port) {
  let best = Infinity;
  for (let i = 1; i < route.length; i++) {
    const out = legDistance(route[i - 1], port);
    const back = legDistance(port, route[i]);
    const direct = legDistance(route[i - 1], route[i]);
    if (out === null || back === null || direct === null) continue;
    best = Math.min(best, out + back - direct);
  }
  // carrying on to it and stopping there: no leg to rejoin, so no way back
  const onward = route.length ? legDistance(route[route.length - 1], port) : null;
  if (onward !== null) best = Math.min(best, onward);
  // the charted legs are measured, not derived, so a triangle can come out
  // very slightly the wrong way round; a detour is never less than nothing
  return best === Infinity ? null : routeSeconds(Math.max(0, best), 0, 0);
}

/* ---- the panel ---- */

/** One row per board, best stop first. Boards that offer nothing usable are
    counted rather than listed: the interesting fact about them is that there
    are so many. */
export function renderBoardPanel(boards) {
  const panel = $('#boards-panel');
  panel.toggleAttribute('hidden', boards.length === 0);
  if (!boards.length) return;

  const live = boards.filter((b) => b.value > 0);
  const rate = currentTrip().rate;
  $('#boards-note').textContent = live.length
    ? `Priced against your trip's ${round(rate)} xp/hr: what an average draw is ` +
      'worth over and above sailing on.'
    : 'Nothing on any board beats sailing on at this rate.';

  $('#boards-rows').innerHTML = live.map((b) => `
    <tr>
      <td>${esc(b.port)}</td>
      <td class="num muted">${b.detour === null ? '&mdash;'
        : b.detour === 0 ? 'on the trip' : formatDuration(b.detour)}</td>
      <td class="num board-value" title="${esc(
        `An average draw of ${b.offers} offers from ${b.port}'s ${b.pool} tasks, ` +
        `keeping the best ${state.freeSlots}. ${b.live} of the ${b.pool} would be ` +
        `worth taking, so ${b.pool - b.live} are dead draws.`)}">${round(b.value)}</td>
      <td class="num">${b.live}<span class="muted">/${b.pool}</span></td>
      <td class="num">${round(b.best)}</td>
    </tr>`).join('');

  const dead = boards.length - live.length;
  $('#boards-dead').textContent = dead
    ? `${dead} more board${dead === 1 ? '' : 's'} offer nothing worth the stop.`
    : '';
}
