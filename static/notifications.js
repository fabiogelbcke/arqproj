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
