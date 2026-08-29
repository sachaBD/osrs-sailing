/* Pricing a task, and pricing a whole trip: how far the cargo travels, how
   long that takes, what it pays.

   For a single task the clock starts when you take the
   cargo aboard at the origin and stops when you hand it over at the
   destination, so it counts one sailing leg and two port calls. It does not
   count getting to the origin in the first place - for an inbound task, whose
   notice board is at the destination, that omitted sail back out is the whole
   leg again. Read inbound rates as a ceiling.

   Every constant comes from tables/params.tsv, and half of them are still
   guesses; see COST_NOTE. */
import { LEGS, COSTS } from './generated.js';

/** Charted sailing distance in game tiles, or null for an uncharted pair. */
export function legDistance(from, to) {
  const row = LEGS[from];
  const d = row ? row[to] : undefined;
  return d === undefined ? null : d;
}

/** Ticks to sail a leg and work the cargo at both ends of it. */
export function taskTicks(task) {
  const d = legDistance(task.from, task.to);
  // load at the origin, unload at the destination: two stops, two actions
  return d === null ? null : routeTicks(d, COSTS.stops, COSTS.stops);
}

export function taskSeconds(task) {
  const ticks = taskTicks(task);
  return ticks === null ? null : ticks * COSTS.tick;
}

/** Experience per hour of that leg, or null when either half is unknown. */
export function taskXpPerHour(task) {
  const seconds = taskSeconds(task);
  if (seconds === null || !seconds || task.xp === null) return null;
  return (task.xp / seconds) * 3600;
}

/** Ticks to sail `tiles` and work `stops` port calls doing `actions` loads
    and unloads between them.

    A single task is the two-stop, two-action case of this, so the two agree
    by construction. Docking is charged per stop and cargo per action, which
    is a guess at how a stop with three deliveries actually plays: only the
    per-stop figure has ever been measured. */
export function routeTicks(tiles, stops, actions) {
  return Math.ceil(tiles / COSTS.sailSpeed) + stops * COSTS.tDock + actions * COSTS.tCargo;
}

export const routeSeconds = (tiles, stops, actions) =>
  routeTicks(tiles, stops, actions) * COSTS.tick;

/** m:ss, or h:mm:ss once a trip runs past the hour. */
export function formatDuration(seconds) {
  if (seconds === null) return null;
  const whole = Math.round(seconds);
  const mm = Math.floor(whole / 60) % 60;
  const ss = String(whole % 60).padStart(2, '0');
  if (whole < 3600) return `${Math.floor(whole / 60)}:${ss}`;
  return `${Math.floor(whole / 3600)}:${String(mm).padStart(2, '0')}:${ss}`;
}

export const COST_NOTE =
  `Sailing at ${COSTS.sailSpeed} tiles/tick, plus ${COSTS.tDock + COSTS.tCargo} ticks ` +
  `of docking and cargo handling at each end. Docking time is still a guess.`;
