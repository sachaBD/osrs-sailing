/* Plane geometry over game coordinates. Straight lines only: real sailing goes
   around land, so these compare options rather than predict travel. */

export const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

/** Shortest distance from point p to the segment a-b. */
export function distanceToSegment(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq === 0) return distance(p, a);
  // how far along the segment the nearest point lies, clamped to its ends
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lengthSq));
  return distance(p, [a[0] + t * dx, a[1] + t * dy]);
}
