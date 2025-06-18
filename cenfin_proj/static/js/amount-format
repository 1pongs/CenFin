function formatInput(el) {
  const raw = el.value.replace(/,/g, '').replace(/[^0-9.]/g, '');
  if (raw === '') {
    el.dataset.raw = '';
    el.value = '';
    return;
  }
  const parts = raw.split('.');
  const intPart = parts[0];
  const decPart = parts[1] ? parts[1].slice(0, 2) : '';
  const formatted = Number(intPart).toLocaleString('en-US') + (decPart ? '.' + decPart : '');
  el.value = formatted;
  el.dataset.raw = intPart + (decPart ? '.' + decPart : '');
}

function attachFormatters() {
  document.querySelectorAll('input.amount-input').forEach(el => {
    el.addEventListener('input', () => formatInput(el));
    const form = el.closest('form');
    if (form) {
      form.addEventListener('submit', () => {
        if (el.dataset.raw !== undefined) {
          el.value = el.dataset.raw;
        }
      });
    }
    // initial format when form rendered with value
    if (el.value) {
      formatInput(el);
    }
  });
}

if (document.readyState !== 'loading') {
  attachFormatters();
} else {
  document.addEventListener('DOMContentLoaded', attachFormatters);
}