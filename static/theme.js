(() => {
  const root = document.documentElement;
  let theme = 'dark';
  try {
    if (localStorage.getItem('arq-theme') === 'light') theme = 'light';
  } catch (_) { /* The toggle also works when storage is unavailable. */ }
  root.dataset.theme = theme;

  document.addEventListener('DOMContentLoaded', () => {
    const button = document.querySelector('.theme-toggle');
    if (!button) return;
    const render = () => {
      const dark = root.dataset.theme === 'dark';
      button.textContent = dark ? button.dataset.lightLabel : button.dataset.darkLabel;
      button.setAttribute('aria-pressed', String(dark));
      document.querySelectorAll('img[data-light-src]').forEach(logo => {
        logo.src = dark && logo.dataset.darkSrc ? logo.dataset.darkSrc : logo.dataset.lightSrc;
      });
    };
    button.hidden = false;
    render();
    button.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('arq-theme', root.dataset.theme); } catch (_) {}
      render();
    });
  });
})();
