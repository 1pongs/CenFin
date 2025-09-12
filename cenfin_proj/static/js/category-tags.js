document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('id_category_names');
  const txTypeSel = document.getElementById('id_transaction_type');
  const entSrcSel = document.getElementById('id_entity_source');
  const entDestSel = document.getElementById('id_entity_destination');
  const entSel = document.getElementById('id_entity');
  const listEl = document.getElementById('category-list');
  const addInput = document.getElementById('new-category');
  const addBtn = document.getElementById('btn-add-category');
  const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]').value;

  // Use trailing slash to avoid 301 redirects that break PATCH/DELETE
  const TAGS_BASE = '/transactions/tags/';
  let tagify = null;
  if (input && !listEl) { // Only init Tagify on non-manager pages
    tagify = new Tagify(input, {
      originalInputValueFormat: values => values.map(v => v.value).join(','),
      dropdown: { maxItems: 20, classname: 'tags-look', closeOnSelect: false }
    });
  }

  function currentEntity() {
    if (entSel) return entSel.value;
    const type = txTypeSel.value;
    if (type === 'income' || type === 'transfer') return entDestSel.value;
    if (type === 'expense') return entSrcSel.value;
    return '';
  }

  function updateAddState(){
    const t = txTypeSel ? txTypeSel.value : '';
    // Disable add when no entity, no type, or viewing "All Types"
    const ready = Boolean((entSel && entSel.value) && t && t !== 'all');
    if (addInput) addInput.disabled = !ready;
    if (addBtn) addBtn.disabled = !ready;
  }

  async function loadTags() {
    const type = txTypeSel ? txTypeSel.value : '';
    // On forms (Tagify present), require specific type. On manager page (list view), allow 'all'.
    if (tagify && !type) return;
    const ent = currentEntity();
    const params = new URLSearchParams();
    if (type && type !== 'all') params.append('transaction_type', type);
    if (ent) params.append('entity', ent);
    const url = `${TAGS_BASE}${params.toString() ? `?${params.toString()}` : ''}`;
    const resp = await fetch(url);
    if (!resp.ok) return;
    const data = await resp.json();
    if (tagify) {
      tagify.settings.whitelist = data.map(t => ({ value: t.name, id: t.id }));
    }
    if (listEl) renderList(data);
  }

  function titleCaseType(s){
    const str = (s || '').toString().replace(/_/g, ' ');
    return str ? str.replace(/\b\w/g, c => c.toUpperCase()) : '—';
  }

  function renderList(items){
    if (!listEl) return;
    listEl.innerHTML = '';
    if (!items || !items.length){
      const li = document.createElement('li');
      li.className = 'list-group-item text-muted';
      li.textContent = 'No categories yet.';
      listEl.appendChild(li);
      return;
    }
    items.forEach(it => {
      const li = document.createElement('li');
      li.className = 'list-group-item d-flex justify-content-between align-items-center';
      li.dataset.id = it.id;
      li.dataset.value = it.name;
      const span = document.createElement('span');
      span.innerHTML = `${it.name} <span class="badge bg-secondary ms-2">${titleCaseType(it.transaction_type)}</span>`;
      const actions = document.createElement('div');
      const btnE = document.createElement('button');
      btnE.type = 'button';
      btnE.className = 'btn btn-sm btn-outline-primary me-2 edit-cat';
      btnE.textContent = 'Edit';
      const btnD = document.createElement('button');
      btnD.type = 'button';
      btnD.className = 'btn btn-sm btn-outline-danger delete-cat';
      btnD.textContent = 'Delete';
      actions.appendChild(btnE);
      actions.appendChild(btnD);
      li.appendChild(span);
      li.appendChild(actions);
      listEl.appendChild(li);
    });
  }

  if (tagify) tagify.on('focus', loadTags);
  txTypeSel && txTypeSel.addEventListener('change', () => {
    if (tagify) tagify.removeAllTags();
    loadTags();
    updateAddState();
  });
  entSrcSel && entSrcSel.addEventListener('change', loadTags);
  entDestSel && entDestSel.addEventListener('change', loadTags);
  entSel && entSel.addEventListener('change', () => { loadTags(); updateAddState(); });

  if (tagify) {
    tagify.on('add', async e => {
      if (e.detail.data.id) return;
      const fd = new FormData();
      fd.append('name', e.detail.data.value);
      fd.append('transaction_type', txTypeSel.value);
      const ent = currentEntity();
      if (ent) fd.append('entity', ent);
      fd.append('csrfmiddlewaretoken', csrf);
      const resp = await fetch(TAGS_BASE, { method: 'POST', body: fd });
      if (resp.ok) {
        const data = await resp.json();
        tagify.replaceTag(e.detail.tag, { value: data.name, id: data.id });
        tagify.settings.whitelist.push({ value: data.name, id: data.id });
      }
    });
  }

  // Manager page explicit Add button
  async function addCategoryByName(name){
    const trimmed = (name || '').trim();
    if (!trimmed) return;
    if (!txTypeSel || !txTypeSel.value){ alert('Select a Type first.'); return; }
    const fd = new FormData();
    fd.append('name', trimmed);
    fd.append('transaction_type', txTypeSel.value);
    const ent = currentEntity();
    if (ent) fd.append('entity', ent);
    fd.append('csrfmiddlewaretoken', csrf);
    const resp = await fetch(TAGS_BASE, { method: 'POST', body: fd });
    if (resp.ok) {
      if (addInput) addInput.value = '';
      await loadTags();
    }
  }
  if (addBtn) addBtn.addEventListener('click', () => addCategoryByName(addInput.value));
  if (addInput) addInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); addCategoryByName(addInput.value); }
  });

  if (tagify) {
    tagify.settings.templates.dropdownItem = function(tagData){
      return `<div ${this.getAttributes(tagData)} class="tagify__dropdown__item d-flex justify-content-between align-items-center">
        <span>${tagData.value}</span>
        <span class="ms-2">
          <span class="edit-tag" style="cursor:pointer;">✏️</span>
          <span class="ms-1 delete-tag" style="cursor:pointer;">🗑</span>
        </span>
      </div>`;
    };
  }

  document.addEventListener('click', async ev => {
    if (listEl && ev.target.classList.contains('edit-cat')){
      const li = ev.target.closest('li[data-id]');
      const id = li.dataset.id;
      const oldName = li.dataset.value;
      const name = prompt('Rename category', oldName);
      if (!name || name === oldName) return;
      const resp = await fetch(`${TAGS_BASE}${id}/`, {
        method: 'PATCH',
        headers: {'X-CSRFToken': csrf, 'Content-Type': 'application/x-www-form-urlencoded'},
        body: `name=${encodeURIComponent(name)}`
      });
      if (resp.ok) loadTags();
      return;
    }
    if (listEl && ev.target.classList.contains('delete-cat')){
      const li = ev.target.closest('li[data-id]');
      const id = li.dataset.id;
      if (!confirm('Delete this category?')) return;
      const resp = await fetch(`${TAGS_BASE}${id}/`, { method: 'DELETE', headers: {'X-CSRFToken': csrf} });
      if (resp.ok) loadTags();
      return;
    }
    if (ev.target.classList.contains('edit-tag')) {
      ev.stopPropagation();
      const item = ev.target.closest('[data-id]');
      const id = item.dataset.id;
      const oldName = item.dataset.value;
      const name = prompt('Rename tag', oldName);
      if (!name || name === oldName) return;
      const resp = await fetch(`${TAGS_BASE}${id}/`, {
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
      const resp = await fetch(`${TAGS_BASE}${id}/`, {
        method: 'DELETE',
        headers: {'X-CSRFToken': csrf}
      });
      if (resp.ok) {
        await loadTags();
      }
    }
  });

  // Initial load: on manager page, load even if type is 'all'
  if (entSel && entSel.value && txTypeSel){
    loadTags();
  }
  updateAddState();
});
