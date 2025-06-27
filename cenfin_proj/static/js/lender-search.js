function setupSearchCreate(textId, hiddenId, apiUrl){
  const input = document.getElementById(textId);
  const hidden = document.getElementById(hiddenId);
  if(!input || !hidden) return;
  const list = document.getElementById(input.getAttribute('list'));
  const modalEl = document.getElementById(textId + '-modal');
  const modal = new bootstrap.Modal(modalEl);
  const nameSpan = modalEl.querySelector('.new-name');
  const dupMsg = modalEl.querySelector('.dup-msg');
  const confirmBtn = modalEl.querySelector('.confirm-btn');
  let cache = {};

  async function search(term){
    if(!term) return;
    const resp = await fetch(`${apiUrl}?q=${encodeURIComponent(term)}`, {credentials:'same-origin'});
    if(resp.ok){
      const data = await resp.json();
      list.innerHTML = '';
      cache = {};
      data.results.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.name;
        opt.dataset.id = r.id;
        list.appendChild(opt);
        cache[r.name] = r.id;
      });
    }
  }

  input.addEventListener('input', () => {
    search(input.value);
    if(cache[input.value] !== undefined){
      hidden.value = cache[input.value];
    } else {
      hidden.value = '';
    }
  });

  input.form.addEventListener('submit', e => {
    if(hidden.value || !input.value.trim()) return;
    e.preventDefault();
    nameSpan.textContent = input.value;
    dupMsg.style.display = 'none';
    confirmBtn.dataset.name = input.value;
    confirmBtn.dataset.force = '';
    modal.show();
  });

  confirmBtn.addEventListener('click', async () => {
    const name = confirmBtn.dataset.name;
    const fd = new FormData();
    fd.append('name', name);
    if(confirmBtn.dataset.force) fd.append('force', '1');
    const resp = await fetch(apiUrl, {method:'POST', body:fd, credentials:'same-origin'});
    if(resp.status === 409){
      const data = await resp.json();
      dupMsg.textContent = `${name} looks similar to ${data.similar.name}`;
      dupMsg.style.display = '';
      confirmBtn.dataset.force = '1';
    }else if(resp.ok){
      const data = await resp.json();
      hidden.value = data.id;
      input.value = data.name;
      modal.hide();
      input.form.requestSubmit();
    }else{
      modal.hide();
      input.form.requestSubmit();
    }
  });
}
window.setupSearchCreate = setupSearchCreate;