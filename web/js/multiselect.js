/* A dropdown of checkboxes backed by a Set.

   The Set is held by reference, so callers must mutate it rather than replace
   it; `apply()` re-reads it after any outside change. */
import { $, $$, esc } from './dom.js';

export function multiSelect(rootSelector, values, placeholder, selected, onChange) {
  const root = $(rootSelector);
  root.innerHTML = `
    <button type="button" class="ms-button">
      <span class="ms-label">${esc(placeholder)}</span><span class="ms-caret">&#9662;</span>
    </button>
    <div class="ms-menu" hidden>
      <div class="ms-actions">
        <button type="button" data-act="all">All</button>
        <button type="button" data-act="none">None</button>
      </div>
      <div class="ms-options">${values.map((v) =>
        `<label><input type="checkbox" value="${esc(v)}"><span>${esc(v)}</span></label>`).join('')}</div>
    </div>`;

  const button = $('.ms-button', root);
  const menu = $('.ms-menu', root);
  const label = $('.ms-label', root);

  const syncLabel = () => {
    label.textContent = selected.size === 0 ? placeholder
      : selected.size === 1 ? [...selected][0]
      : `${selected.size} selected`;
    button.classList.toggle('active', selected.size > 0);
  };

  button.addEventListener('click', () => {
    const opening = menu.hidden;
    $$('.ms-menu').forEach((m) => { m.hidden = true; });
    menu.hidden = !opening;
  });

  menu.addEventListener('change', (e) => {
    if (e.target.checked) selected.add(e.target.value); else selected.delete(e.target.value);
    syncLabel();
    onChange();
  });

  $('.ms-actions', root).addEventListener('click', (e) => {
    const act = e.target.dataset.act;
    if (!act) return;
    selected.clear();
    if (act === 'all') values.forEach((v) => selected.add(v));
    $$('input', menu).forEach((i) => { i.checked = act === 'all'; });
    syncLabel();
    onChange();
  });

  const api = {
    apply() {
      $$('input', menu).forEach((i) => { i.checked = selected.has(i.value); });
      syncLabel();
    },
    reset() {
      selected.clear();
      menu.hidden = true;
      api.apply();
    },
  };
  root._multi = api;
  api.apply();
  return api;
}

/** One document-level handler closes any open menu. */
export function closeMenusOnOutsideClick() {
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.ms')) $$('.ms-menu').forEach((m) => { m.hidden = true; });
  });
}
