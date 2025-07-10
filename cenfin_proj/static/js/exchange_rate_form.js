document.addEventListener('DOMContentLoaded', () => {
  const srcSel = document.getElementById('id_source');
  const fromSel = document.getElementById('id_currency_from');
  const toSel = document.getElementById('id_currency_to');
  const saveBtn = document.querySelector('input[name="save"], button[name="save"]');
  if(!srcSel || !fromSel || !toSel) return;

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

  function renderOptions(list){
    const currentFrom = fromSel.value;
    const currentTo = toSel.value;
    fromSel.innerHTML = '';
    toSel.innerHTML = '';
    list.forEach(item => {
      const opt1 = new Option(`${item.code} – ${item.name}`, item.id, false, item.id == currentFrom);
      const opt2 = new Option(`${item.code} – ${item.name}`, item.id, false, item.id == currentTo);
      fromSel.appendChild(opt1);
      toSel.appendChild(opt2.cloneNode(true));
    });
  }

  async function loadCurrencies(){
    const source = srcSel.value;
    if(!source){
      fromSel.innerHTML = '';
      toSel.innerHTML = '';
      if(saveBtn) saveBtn.disabled = true;
      return;
    }
    if(saveBtn) saveBtn.disabled = true;
    try{
      const resp = await fetch(`/currencies/list/${source}/`);
      if(!resp.ok) throw new Error('bad');
      const data = await resp.json();
      if(data.currencies){
        renderOptions(data.currencies);
        if(saveBtn) saveBtn.disabled = false;
      }else{
        throw new Error('bad');
      }
    }catch(err){
      showToast('Error loading currencies');
      if(saveBtn) saveBtn.disabled = true;
    }
  }

  srcSel.addEventListener('change', loadCurrencies);
  if(srcSel.value){
    loadCurrencies();
  }
});