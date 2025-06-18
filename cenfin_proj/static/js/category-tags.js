document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('id_category_names');
  if (!input) return;
  const txTypeSel = document.getElementById('id_transaction_type');
  const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

  const tagify = new Tagify(input, {
    originalInputValueFormat: values => values.map(v => v.value).join(','),
    dropdown: { maxItems: 20, classname: 'tags-look', closeOnSelect: false }
  });

  async function loadTags() {
    const type = txTypeSel.value;
    if (!type) return;
    const resp = await fetch(`/tags?transaction_type=${encodeURIComponent(type)}`);
    if (resp.ok) {
      const data = await resp.json();
      tagify.settings.whitelist = data.map(t => ({ value: t.name, id: t.id }));
    }
  }

  tagify.on('focus', loadTags);
  txTypeSel.addEventListener('change', () => {
    tagify.removeAllTags();
    loadTags();
  });

  tagify.on('add', async e => {
    if (e.detail.data.id) return;
    const fd = new FormData();
    fd.append('name', e.detail.data.value);
    fd.append('transaction_type', txTypeSel.value);
    fd.append('csrfmiddlewaretoken', csrf);
    const resp = await fetch('/tags', { method: 'POST', body: fd });
    if (resp.ok) {
      const data = await resp.json();
      tagify.replaceTag(e.detail.tag, { value: data.name, id: data.id });
      tagify.settings.whitelist.push({ value: data.name, id: data.id });
    }
  });

  tagify.settings.templates.dropdownItem = function(tagData){
    return `<div ${this.getAttributes(tagData)} class="tagify__dropdown__item d-flex justify-content-between align-items-center">
      <span>${tagData.value}</span>
      <span class="ms-2">
        <span class="edit-tag" style="cursor:pointer;">✏️</span>
        <span class="ms-1 delete-tag" style="cursor:pointer;">🗑</span>
      </span>
    </div>`;
  };

  document.addEventListener('click', async ev => {
    if (ev.target.classList.contains('edit-tag')) {
      ev.stopPropagation();
      const item = ev.target.closest('[data-id]');
      const id = item.dataset.id;
      const oldName = item.dataset.value;
      const name = prompt('Rename tag', oldName);
      if (!name || name === oldName) return;
      const resp = await fetch(`/tags/${id}`, {
        method: 'PATCH',
        headers: {'X-CSRFToken': csrf, 'Content-Type': 'application/x-www-form-urlencoded'},
        body: `name=${encodeURIComponent(name)}`
      });
      if (resp.ok) {
        await loadTags();
      }
    } else if (ev.target.classList.contains('delete-tag')) {
      ev.stopPropagation();
      const item = ev.target.closest('[data-id]');
      const id = item.dataset.id;
      if (!confirm('Delete this tag?')) return;
      const resp = await fetch(`/tags/${id}`, {
        method: 'DELETE',
        headers: {'X-CSRFToken': csrf}
      });
      if (resp.ok) {
        await loadTags();
      }
    }
  });
});