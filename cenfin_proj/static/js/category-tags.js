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
  const bannerHost = document.getElementById('inline-banner');

  // Use trailing slash to avoid 301 redirects that break PATCH/DELETE
  const TAGS_BASE = '/transactions/tags/';
  // Support two modes: Tagify input (legacy) or a select input with id 'id_category'
  let tagify = null;
  const categorySelect = document.getElementById('id_category');
  // If the server rendered a selected category but the select hasn't been
  // touched yet by client scripts, show a temporary option right away so
  // users see the saved value even if AJAX runs later or is slow.
  if (categorySelect) {
    try {
      const dataPrevId = categorySelect.getAttribute('data-selected-id') || '';
      const dataPrevText = categorySelect.getAttribute('data-selected-text') || '';
      if (dataPrevId && !Array.from(categorySelect.options).some(o => o.value === String(dataPrevId))) {
        const tmp = document.createElement('option');
        tmp.value = dataPrevId;
        tmp.textContent = dataPrevText || 'Selected';
        // Insert as first option after placeholder if present
        const first = categorySelect.options[0] || null;
        categorySelect.insertBefore(tmp, first ? first.nextSibling : null);
        categorySelect.value = dataPrevId;
      }
    } catch (e) {
      // non-fatal; allow normal flow
    }
  }
  if (input && !listEl) { // legacy Tagify mode
    tagify = new Tagify(input, {
      originalInputValueFormat: values => values.map(v => v.value).join(','),
      dropdown: { maxItems: 20, classname: 'tags-look', closeOnSelect: false }
    });
    try { window.categoryTagify = tagify; } catch (e) {}
  }

  function currentEntity() {
    if (entSel) return entSel.value;
    const type = txTypeSel.value;
    // If a global entity-side mapping is present (in templates we set
    // `entitySideMap`), prefer it. Support lookup by both the raw value
    // (which may be underscore_separated) and a space-separated variant
    // so the mapping is resilient to key formatting.
    try {
      const map = window.entitySideMap || null;
      if (map && type) {
        // Prefer a normalized underscore key (e.g. 'sell_acquisition') but
        // accept either form for backward compatibility.
        const keyUnderscore = type.toString().replace(/ /g, '_');
        const direct = map[type];
        const underscored = map[keyUnderscore];
        const primary = underscored || direct;
        if (primary === 'destination') return entDestSel ? entDestSel.value : '';
        if (primary === 'source') return entSrcSel ? entSrcSel.value : '';
      }
    } catch (e) {
      // ignore and fall back to legacy behavior
    }
    if (type === 'income' || type === 'transfer') return entDestSel ? entDestSel.value : '';
    if (type === 'expense') return entSrcSel ? entSrcSel.value : '';
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
  const rawType = txTypeSel ? (txTypeSel.value || '') : '';
  // Normalize transaction_type to lowercase underscore form to match
  // server storage (e.g. 'Sell Acquisition' -> 'sell_acquisition').
  const type = rawType ? rawType.toString().toLowerCase().replace(/ /g, '_') : '';
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
    if (categorySelect) {
      // preserve currently-selected value so we don't clobber a server-
      // rendered selected option when loadTags runs after the page has
      // already set an initial selection (common on Edit pages).
  // Prefer explicit data attributes set by server-rendered widget for
  // the previously-selected category (more reliable than relying on
  // the DOM selection state which can be changed by later JS).
  const dataPrevId = categorySelect.getAttribute('data-selected-id') || '';
  const dataPrevText = categorySelect.getAttribute('data-selected-text') || '';
  const prev = dataPrevId || categorySelect.value || '';
  // preserve the currently-visible label text in case the server
      // returns a different set that doesn't include the selected id.
      // Prefer the option that matches the current value (may not be
      // selectedIndex if browser defaulting differs), fall back to
      // selectedIndex.
  let prevText = dataPrevText || '';
      if (prev) {
        const prevOpt = Array.from(categorySelect.options).find(o => o.value === prev);
        if (prevOpt) prevText = prevOpt.text || '';
      }
      if (!prevText) prevText = (categorySelect.options[categorySelect.selectedIndex] || {}).text || '';
      // If there is a previous selection (from server-rendered initial
      // state), preserve existing options and only append/update the
      // tags returned by the API so we don't remove the selected option.
      if (!prev) {
        categorySelect.innerHTML = '<option value="">-----------</option>';
        data.forEach(t => {
          const opt = document.createElement('option');
          opt.value = t.id;
          opt.textContent = t.name;
          categorySelect.appendChild(opt);
        });
      } else {
        // Build a map of existing options (value -> option element)
        const existing = {};
        Array.from(categorySelect.options).forEach(o => { existing[o.value] = o; });
        // Ensure placeholder exists
        if (!existing['']) {
          const ph = document.createElement('option');
          ph.value = '';
          ph.textContent = '-----------';
          categorySelect.insertBefore(ph, categorySelect.firstChild || null);
        }
        // Add or update options from API without removing existing ones
        data.forEach(t => {
          const key = String(t.id);
          if (existing[key]) {
            // update label if changed
            existing[key].textContent = t.name;
          } else {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name;
            categorySelect.appendChild(opt);
          }
        });
      }
      try {
        // (debug output removed)
      } catch (e) {}
      // Try to restore previous selection if it's still available
      if (prev) {
        const found = Array.from(categorySelect.options).some(o => o.value === prev);
        if (found) {
            categorySelect.value = prev;
        }
        else if (prevText) {
          // create a temporary option so the UI still shows the selected
          // text even if the API didn't return the tag (for example when
          // tags were recently deleted or scoped differently).
          const tmp = document.createElement('option');
          tmp.value = prev;
          tmp.textContent = prevText;
          // Insert at top after placeholder
          categorySelect.insertBefore(tmp, categorySelect.options[1] || null);
          categorySelect.value = prev;
        }
        // Ensure the corresponding option element is explicitly marked selected
        try {
        const selOpt = Array.from(categorySelect.options).find(o => o.value === String(prev));
        if (selOpt) selOpt.selected = true;
        // notify listeners about the change (balance summary logic listens)
        categorySelect.dispatchEvent(new Event('change', { bubbles: true }));
        } catch (e) {
          // non-fatal
        }
      }
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

  function showUndoBanner(message, undoUrl){
    if (!bannerHost) return;
    bannerHost.innerHTML = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'alert alert-success d-flex justify-content-between align-items-center';
    const text = document.createElement('div');
    text.textContent = message;
    const actions = document.createElement('div');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm btn-success';
    btn.textContent = 'Undo';
    btn.addEventListener('click', async () => {
      const resp = await fetch(undoUrl, { method: 'POST', headers: { 'X-CSRFToken': csrf } });
      if (resp.ok) {
        await loadTags();
        bannerHost.innerHTML = '';
      }
    });
    actions.appendChild(btn);
    wrapper.appendChild(text);
    wrapper.appendChild(actions);
    bannerHost.appendChild(wrapper);
  }

  if (tagify) tagify.on('focus', loadTags);
  const refreshOnTypeChange = () => { if (tagify) tagify.removeAllTags(); loadTags(); updateAddState(); };
  txTypeSel && txTypeSel.addEventListener('change', refreshOnTypeChange);
  entSrcSel && entSrcSel.addEventListener('change', loadTags);
  entDestSel && entDestSel.addEventListener('change', loadTags);
  entSel && entSel.addEventListener('change', () => { loadTags(); updateAddState(); });

  if (tagify) {
    tagify.on('add', async e => {
      if (e.detail.data.id) return;
      const fd = new FormData();
      fd.append('name', e.detail.data.value);
  fd.append('transaction_type', txTypeSel && txTypeSel.value ? txTypeSel.value.toString().toLowerCase().replace(/ /g, '_') : '');
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
  fd.append('transaction_type', txTypeSel && txTypeSel.value ? txTypeSel.value.toString().toLowerCase().replace(/ /g, '_') : '');
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
      if (resp.ok) {
        const data = await resp.json().catch(() => ({}));
        await loadTags();
        if (data.undo_url) {
          showUndoBanner('Category deleted.', data.undo_url);
        }
      }
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
        const data = await resp.json().catch(() => ({}));
        await loadTags();
        if (data.undo_url) {
          showUndoBanner('Category deleted.', data.undo_url);
        }
      }
    }
  });

  // Initial load: populate the category <select> on forms as well as the
  // manager page. This ensures the client-side filter (transaction_type +
  // entity) is applied and replaces any server-rendered options that may
  // include unrelated/global tags.
  // Defer initial load until the global `entitySideMap` has been injected by
  // inline templates. Without this mapping, certain transaction types like
  // 'sell_acquisition' fall back to legacy behavior and won't select the
  // desired primary entity (destination). Retry a few times with short
  // delays before giving up so pages without the mapping still work.
  function scheduleInitialLoad(attempts = 0) {
    const MAX = 10; // ~500ms max wait
    if (window.entitySideMap || attempts > MAX) {
      if (categorySelect && txTypeSel) {
        // call irrespective of entSel presence; the server will handle missing
        // entity params appropriately.
        loadTags();
      } else if (entSel && entSel.value && txTypeSel) {
        // legacy manager page behavior (load even for 'all')
        loadTags();
      }
    } else {
      setTimeout(() => scheduleInitialLoad(attempts + 1), 50);
    }
  }
  scheduleInitialLoad();
  // Defensive retries: some other page scripts may run after loadTags and
  // re-populate or clear the select. Retry a few times to ensure the
  // previously-selected category (provided by server in data attributes)
  // is visible to the user.
  function restorePrevOnce(){
    if (!categorySelect) return;
    const dataPrevId = categorySelect.getAttribute('data-selected-id') || '';
    const dataPrevText = categorySelect.getAttribute('data-selected-text') || '';
    const curVal = categorySelect.value || '';
    if (dataPrevId && !curVal) {
      // If select lacks a value, try to find the option or insert fallback
      const found = Array.from(categorySelect.options).some(o => o.value === dataPrevId);
      if (found) {
        categorySelect.value = dataPrevId;
        try { categorySelect.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
        return true;
      }
      if (dataPrevText) {
        const tmp = document.createElement('option');
        tmp.value = dataPrevId;
        tmp.textContent = dataPrevText;
        categorySelect.insertBefore(tmp, categorySelect.options[1] || null);
        categorySelect.value = dataPrevId;
        try { categorySelect.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
        return true;
      }
    }
    return false;
  }
  // schedule several retries over the first second to handle races with
  // other scripts that may clear or re-populate the select. We attempt a
  // few retries and then give up; duplicate retries are unnecessary, so
  // keep a single schedule here.
  [100, 300, 700].forEach(delay => setTimeout(() => { try { restorePrevOnce(); } catch (e) {} }, delay));
  updateAddState();
});
