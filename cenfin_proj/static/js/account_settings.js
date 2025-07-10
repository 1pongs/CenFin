(function(){
  document.addEventListener('DOMContentLoaded', function(){
    const form = document.getElementById('account-settings-form');
    if(!form) return;
    const saveBtn = form.querySelector('input[name="save"], button[name="save"]');
    const srcSelect = document.getElementById('id_preferred_rate_source');
    const curDiv = document.getElementById('div_id_base_currency');
    const manage = document.getElementById('manage-rates');
    if(!saveBtn) return;
    
    const fields = Array.from(form.querySelectorAll('input, select, textarea'));
    const initial = fields.map(el => el.type === 'checkbox' || el.type === 'radio' ? el.checked : el.value);

    function checkChanged(){
      let changed = false;
      fields.forEach((el, idx) => {
        const orig = initial[idx];
        const cur = el.type === 'checkbox' || el.type === 'radio' ? el.checked : el.value;
        if(cur != orig) changed = true;
      });
      saveBtn.disabled = !changed;
    }

    function toggleCurrency(){
      const hasSource = srcSelect.value !== '';
      if(curDiv){
        curDiv.classList.toggle('d-none', !hasSource);
        const sel = curDiv.querySelector('select');
        if(sel) sel.disabled = !hasSource;
      }
      if(manage){
        manage.style.display = srcSelect.value === 'USER' ? '' : 'none';
      }
    }

    saveBtn.disabled = true;
    toggleCurrency();
    form.addEventListener('input', checkChanged);
    form.addEventListener('change', checkChanged);
    if(srcSelect){
      srcSelect.addEventListener('change', toggleCurrency);
    }
  });
})();