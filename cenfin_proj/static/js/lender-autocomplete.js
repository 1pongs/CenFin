function setupAutocomplete(textId, hiddenId, searchUrl, createUrl){
  const input = document.getElementById(textId);
  const hidden = document.getElementById(hiddenId);
  if(!input || !hidden) return;
  const list = document.getElementById(input.getAttribute('list'));
  if(!list) return;
  const spinner = document.createElement('div');
  spinner.className = 'spinner-border spinner-border-sm text-secondary ms-2 d-none';
  spinner.role = 'status';
  spinner.innerHTML = '<span class="visually-hidden">Loading...</span>';
  input.insertAdjacentElement('afterend', spinner);
  let cache = {};
  let timer;
  async function search(term){
    if(!term){
      list.innerHTML = '';
      return;
    }
    spinner.classList.remove('d-none');
    const resp = await fetch(`${searchUrl}?q=${encodeURIComponent(term)}`, {credentials:'same-origin'});
    spinner.classList.add('d-none');
    if(resp.ok){
      const data = await resp.json();
      list.innerHTML = '';
      cache = {};
      let found = false;
      data.results.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.text;
        opt.dataset.id = r.id;
        list.appendChild(opt);
        cache[r.text.toLowerCase()] = r.id;
        if(r.text.toLowerCase() === term.toLowerCase()) found = true;
      });
      if(!found){
        const opt = document.createElement('option');
        opt.value = `Add "${term}"...`;
        opt.dataset.add = term;
        list.appendChild(opt);
      }
    }
  }
  input.addEventListener('input', () => {
    hidden.value = '';
    clearTimeout(timer);
    timer = setTimeout(() => search(input.value.trim()), 300);
  });
  input.addEventListener('change', () => {
    const val = input.value.trim();
    const opt = Array.from(list.options).find(o => o.value === val);
    if(opt){
      if(opt.dataset.id){
        hidden.value = opt.dataset.id;
      }else if(opt.dataset.add){
        create(opt.dataset.add);
      }
    }else if(cache[val.toLowerCase()]){
      hidden.value = cache[val.toLowerCase()];
    }
  });
  input.form.addEventListener('submit', e => {
    if(hidden.value || !input.value.trim()) return;
    e.preventDefault();
    create(input.value.trim());
  });
  async function create(name){
    spinner.classList.remove('d-none');
    const fd = new FormData();
    fd.append('name', name);
    const resp = await fetch(createUrl, {method:'POST', body:fd, credentials:'same-origin'});
    spinner.classList.add('d-none');
    if(resp.ok){
      const data = await resp.json();
      hidden.value = data.id;
      input.value = data.text;
    }
    input.form.requestSubmit();
  }
}
window.setupAutocomplete = setupAutocomplete;