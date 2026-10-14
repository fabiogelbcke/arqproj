// Painel modals: open/close <dialog>s, the editable stage list, the project link
// that follows the project name, and the logo file name.
(() => {
  const slugify = (text, { trim = true } = {}) => {
    const slug = text
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().replace(/[^a-z0-9]+/g, '-');
    return trim ? slug.replace(/^-+|-+$/g, '') : slug.replace(/^-+/, '');
  };

  // The last stage can't be removed: a project needs at least one.
  const syncStages = (list) => {
    const buttons = list.querySelectorAll('[data-remove-stage]');
    buttons.forEach((b) => {
      const last = buttons.length === 1;
      b.disabled = last;
      b.title = last ? list.dataset.lastStageLabel : b.getAttribute('aria-label');
    });
  };

  document.addEventListener('click', (e) => {
    const opener = e.target.closest('[data-open-dialog]');
    if (opener) {
      const dialog = document.getElementById(opener.dataset.openDialog);
      if (dialog && !dialog.open) dialog.showModal();
      return;
    }
    if (e.target.closest('[data-close-dialog]')) {
      e.target.closest('dialog')?.close();
      return;
    }
    // A click on the backdrop lands on the <dialog> element itself.
    if (e.target instanceof HTMLDialogElement && !('required' in e.target.dataset)) {
      const r = e.target.getBoundingClientRect();
      const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      if (!inside) e.target.close();
      return;
    }
    if (e.target.closest('[data-add-stage]')) {
      const fieldset = e.target.closest('fieldset');
      const list = fieldset.querySelector('[data-stage-list]');
      const item = fieldset.querySelector('[data-stage-template]').content.firstElementChild.cloneNode(true);
      list.append(item);
      syncStages(list);
      item.querySelector('input').focus();
      return;
    }
    const remove = e.target.closest('[data-remove-stage]');
    if (remove && !remove.disabled) {
      const list = remove.closest('[data-stage-list]');
      const item = remove.closest('li');
      const next = item.nextElementSibling || item.previousElementSibling;
      item.remove();
      syncStages(list);
      (next?.querySelector('input') || document.querySelector('[data-add-stage]'))?.focus();
    }
  });

  // Required dialogs ignore Escape.
  document.addEventListener('cancel', (e) => {
    if (e.target instanceof HTMLDialogElement && 'required' in e.target.dataset) e.preventDefault();
  }, true);

  // New project: flag a name or link another project already uses, before submitting.
  // The server checks again; this only saves a round trip.
  const checkTaken = (form) => {
    const names = new Set(JSON.parse(form.dataset.takenNames));
    const slugs = new Set(JSON.parse(form.dataset.takenSlugs));
    const title = form.querySelector('[name="title"]');
    const slug = form.querySelector('[name="slug"]');
    title.setCustomValidity(names.has(title.value.trim().toLowerCase()) ? form.dataset.nameTaken : '');
    const link = slugify(slug.value) || slugify(title.value);
    slug.setCustomValidity(link && slugs.has(link) ? form.dataset.slugTaken : '');
  };

  document.addEventListener('input', (e) => {
    const field = e.target;
    // The link only accepts lowercase letters, numbers and hyphens: convert as people type.
    if (field.matches('[data-slug-from]')) {
      const clean = slugify(field.value, { trim: false });
      if (clean !== field.value) field.value = clean;
    } else {
      const linked = field.id && document.querySelector(`[data-slug-from="${field.id}"]`);
      if (linked) linked.placeholder = slugify(field.value);
    }
    const form = field.closest('form[data-taken-names]');
    if (form) checkTaken(form);
  });

  document.addEventListener('change', (e) => {
    if (e.target.matches('[data-slug-from]')) e.target.value = slugify(e.target.value);
    if (e.target.matches('.file-pick__input')) {
      const name = e.target.closest('.file-pick').querySelector('[data-file-name]');
      name.dataset.empty ??= name.textContent;
      name.textContent = e.target.files[0]?.name || name.dataset.empty;
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-stage-list]').forEach(syncStages);
    document.querySelectorAll('dialog[data-open-on-load]').forEach((d) => d.showModal());
  });
})();
