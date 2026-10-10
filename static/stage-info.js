document.addEventListener('click', event => {
  document.querySelectorAll('.stage-info[open]').forEach(info => {
    if (!info.contains(event.target)) info.open = false;
  });
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  document.querySelectorAll('.stage-info[open]').forEach(info => {
    info.open = false;
    info.querySelector('summary').focus();
  });
});
