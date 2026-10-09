// Keep the complete project name on one line, including after fonts load.
(() => {
  const title = document.querySelector('.hero__title');
  if (!title) return;

  const fit = () => {
    title.style.fontSize = '';
    const available = title.clientWidth;
    if (!available || title.scrollWidth <= available) return;
    let size = parseFloat(getComputedStyle(title).fontSize);
    size *= available / title.scrollWidth;
    title.style.fontSize = `${size}px`;
    // Account for pixel rounding in the measured width.
    while (title.scrollWidth > available && size > 1) {
      size -= 0.25;
      title.style.fontSize = `${size}px`;
    }
  };

  new ResizeObserver(fit).observe(title.parentElement);
  new MutationObserver(fit).observe(title, { childList: true, characterData: true, subtree: true });
  if (document.fonts) document.fonts.ready.then(fit);
  fit();
})();
