(() => {
  const setExpanded = (stage, expanded) => {
    const button = stage.querySelector('.stage-toggle');
    if (!button) return;
    stage.querySelector('.stage__content').hidden = !expanded;
    button.setAttribute('aria-expanded', String(expanded));
    button.setAttribute('aria-label', expanded ? button.dataset.collapseLabel : button.dataset.expandLabel);
  };
  document.querySelectorAll('.stage--done, .stage--current').forEach(stage => {
    const button = stage.querySelector('.stage-toggle');
    button.hidden = false;
    setExpanded(stage, stage.classList.contains('stage--current'));
    button.addEventListener('click', () => setExpanded(stage, button.getAttribute('aria-expanded') !== 'true'));
    stage.addEventListener('stage:reveal', () => setExpanded(stage, true));
  });
  const revealHash = hash => {
    const stage = document.getElementById(hash.slice(1));
    if (stage?.classList.contains('stage')) setExpanded(stage, true);
  };
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#stage-"]');
    if (link) revealHash(link.getAttribute('href'));
  });
  window.addEventListener('hashchange', () => revealHash(location.hash));
  revealHash(location.hash);
})();
