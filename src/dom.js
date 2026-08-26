/* Small DOM helpers. Views build HTML as strings, so `esc` is not optional:
   port names such as "Land's End" carry characters that break attributes. */

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ESCAPES[c]);

/** localStorage that stays quiet when it is unavailable (private mode, full). */
export function store(key, value) {
  try {
    if (value) localStorage.setItem(key, value); else localStorage.removeItem(key);
  } catch (_) { /* persistence is a nicety, never a hard requirement */ }
}

export function stored(key) {
  try { return localStorage.getItem(key); } catch (_) { return null; }
}
