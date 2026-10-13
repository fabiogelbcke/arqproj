const notifications = document.querySelector('.notifications');
if (notifications) {
  const storageKey = 'arq-notifications:' + location.pathname;
  const keys = Array.from(notifications.querySelectorAll('[data-update-key]'), item => item.dataset.updateKey);
  let seen = [];
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
    if (Array.isArray(saved)) seen = saved;
  } catch (_) {}
  const unread = keys.filter(key => !seen.includes(key)).length;
  const badge = notifications.querySelector('.notifications__badge');
  const summary = notifications.querySelector('summary');
  const label = summary.getAttribute('aria-label');
  badge.textContent = String(unread);
  badge.hidden = unread === 0;
  if (unread) summary.setAttribute('aria-label', label + ', ' + notifications.dataset.unreadLabel.replace('{n}', unread));
  notifications.addEventListener('toggle', () => {
    if (!notifications.open) return;
    try { localStorage.setItem(storageKey, JSON.stringify(keys)); } catch (_) {}
    badge.hidden = true;
    summary.setAttribute('aria-label', label);
  });
}

document.querySelectorAll('.notifications a[href^="#"]').forEach(link => {
  link.addEventListener('click', () => {
    link.closest('.notifications').open = false;
    const search = document.querySelector('#file-search');
    if (search && search.value) {
      search.value = '';
      search.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
});
