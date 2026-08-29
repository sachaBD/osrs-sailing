/* The water a leg actually follows, for drawing it on the map.

   `cost.js` says how long a leg is; this says which way round the coast it
   goes. The points are the corners a ship must round - `survey.measure` pulls
   each path taut against the water mask - so a run across open sea is two
   points and a threaded strait is thirty.

   Stored one direction per pair (a < b), because the other direction is the
   same water sailed backwards. */
import { COURSES } from './generated.js';

/** Game-coordinate corner points from origin to destination, or [] if uncharted. */
export function courseBetween(origin, destination) {
  if (origin === destination) return [];
  const flip = origin > destination;
  const [a, b] = flip ? [destination, origin] : [origin, destination];
  const row = COURSES[a];
  const course = row ? row[b] : undefined;
  if (!course) return [];
  return flip ? [...course].reverse() : course;
}

/** The whole trip as one run of game coordinates, stop to stop.

    Consecutive legs share a port, so each leg after the first drops its
    opening point rather than repeating it. */
export function courseThrough(ports) {
  const points = [];
  for (let i = 1; i < ports.length; i++) {
    const leg = courseBetween(ports[i - 1], ports[i]);
    if (!leg.length) continue;
    points.push(...(points.length ? leg.slice(1) : leg));
  }
  return points;
}
