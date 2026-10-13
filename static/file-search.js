(() => {
  const control = document.querySelector('.file-search');
  if (!control) return;
  const input = control.querySelector('input');
  const empty = document.querySelector('.file-search__empty');
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  control.hidden = false;
  input.addEventListener('input', () => {
    const query = normalize(input.value.trim());
    let count = 0;
    document.querySelectorAll('.stage').forEach(stage => {
      let stageCount = 0;
      stage.querySelectorAll('.file-group').forEach(group => {
        let groupCount = 0;
        group.querySelectorAll('.files > li').forEach(item => {
          const names = [item.querySelector('.file__name').textContent,
            ...Array.from(item.querySelectorAll('.versions a'), link => link.textContent)];
          item.hidden = query !== '' && !names.some(name => normalize(name).includes(query));
          if (!item.hidden) groupCount++;
        });
        group.hidden = query !== '' && groupCount === 0;
        stageCount += groupCount;
      });
      stage.hidden = query !== '' && stageCount === 0;
      if (query && stageCount > 0) stage.dispatchEvent(new Event('stage:reveal'));
      count += stageCount;
    });
    empty.hidden = query === '' || count > 0;
  });
})();
