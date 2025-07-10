(function(){
  document.addEventListener('DOMContentLoaded', function(){
    const form = document.getElementById('account-settings-form');
    if(!form) return;
    const saveBtn = form.querySelector('input[name="save"], button[name="save"]');
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
    saveBtn.disabled = true;
    form.addEventListener('input', checkChanged);
    form.addEventListener('change', checkChanged);
  });
})();