document.addEventListener('DOMContentLoaded', () => {
  const srcSel = document.getElementById('id_source');
  const fromSel = document.getElementById('id_currency_from');
  const toSel = document.getElementById('id_currency_to');
  const saveBtn = document.querySelector('input[name="save"], button[name="save"]');
  if(!srcSel || !fromSel || !toSel) return;

  function getCookie(name){
    const value = document.cookie
      .split(';')
      .map(v => v.trim())
      .find(v => v.startsWith(name + '='));
    return value ? decodeURIComponent(value.split('=')[1]) : null;
  }

  function showToast(msg, type='danger'){
    const container = document.querySelector('.toast-container');
    if(!container) return;
    const div = document.createElement('div');
    div.className = `toast align-items-center text-bg-${type} border-0 mb-2`;
    div.role = 'alert';
    div.innerHTML = `<div class="d-flex"><div class="toast-body">${msg}</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>`;
    container.appendChild(div);
    bootstrap.Toast.getOrCreateInstance(div, {delay:4000, autohide:true}).show();
  }

  function clearToasts(){
    const container = document.querySelector('.toast-container');
    if(!container) return;
    container.querySelectorAll('.toast').forEach(t => t.remove());
  }

  function renderOptions(map){
      const currentFrom = fromSel.value;
      const currentTo = toSel.value;
      fromSel.innerHTML = '';
      toSel.innerHTML = '';
      Object.entries(map).forEach(([code, name]) => {
        const opt1 = new Option(`${code} – ${name}`, code, false, code == currentFrom);
        const opt2 = new Option(`${code} – ${name}`, code, false, code == currentTo);
        fromSel.appendChild(opt1);
        toSel.appendChild(opt2.cloneNode(true));
      });
    }

  function renderEmpty(){
      fromSel.innerHTML = '<option value="">No currencies available</option>';
      toSel.innerHTML = '<option value="">No currencies available</option>';
  }

  function updateSaveState(){
      if(!saveBtn) return;
      saveBtn.disabled = !(fromSel.value && toSel.value);
  }
  
    async function loadCurrencies(){
    const source = srcSel.value;
    if(!source){
      fromSel.innerHTML = '';
      toSel.innerHTML = '';
      updateSaveState();
      return;
    }
    updateSaveState();
    try{
        const url = `/api/currencies?source=${encodeURIComponent(source)}`;
        const resp = await fetch(url, {
          method: 'GET',
          credentials: 'same-origin',
          headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Accept': 'application/json'
          }
        });
      if(!resp.ok) throw new Error('bad');
      const data = await resp.json();
        if(data && Object.keys(data).length){
            renderOptions(data);
        }else{
            renderEmpty();
        }
      clearToasts();
      updateSaveState();
    }catch(err){
      showToast('Error loading currencies');
      renderEmpty();
      updateSaveState();
    }
  }

  srcSel.addEventListener('change', loadCurrencies);
  fromSel.addEventListener('change', updateSaveState);
  toSel.addEventListener('change', updateSaveState);
  if(srcSel.value){
    loadCurrencies();
  }
});