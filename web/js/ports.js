/* The one place that knows how to read the generated port tables. */
import { TASKS, LOCATIONS, MAP_META } from './generated.js';

export { TASKS, LOCATIONS, MAP_META };

export const TASK_BY_ID = new Map(TASKS.map((t) => [t.id, t]));

const meta = (name) => LOCATIONS[name] || {};

export const regionOf = (name) => meta(name).region || 'Unknown';
export const oceansOf = (name) => meta(name).oceans || [];
export const dockLevelOf = (name) => Number(meta(name).dock_level) || 0;

/** A shipwright is what lets you recover a capsized or parked boat. */
export const canRecoverAt = (name) => meta(name).shipwright === 'yes';

/** Not every port has a notice board, so a follow-up task isn't always there. */
export const hasBoardAt = (name) => meta(name).notice_board === 'yes';

/** World coordinates as [x, y], or null for a port with none recorded. */
export function portXY(name) {
  const coords = meta(name).coords;
  if (!coords) return null;
  const [x, y] = coords.split(',').map(Number);
  return [x, y];
}

/** The three ports a task touches, named as the "Match on" scope names them. */
export const legsOf = (task) => ({ board: task.noticeBoard, from: task.from, to: task.to });

const sortedUnique = (values) => [...new Set(values)].sort((a, b) => a.localeCompare(b));

export const allPorts = sortedUnique(TASKS.flatMap((t) => [t.noticeBoard, t.from, t.to]));
export const allRegions = sortedUnique(Object.values(LOCATIONS).map((v) => v.region));
export const allOceans = sortedUnique(Object.values(LOCATIONS).flatMap((v) => v.oceans));
