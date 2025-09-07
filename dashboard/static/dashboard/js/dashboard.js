document.addEventListener('DOMContentLoaded', () => {
  const bigTicketsEl = document.getElementById('top-big-data');
  const bigTickets = bigTicketsEl ? JSON.parse(bigTicketsEl.textContent || '[]') : [];
  
  function formatPeso(val){
    return `\u20B1${Number(val).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
  }

  const ctx1 = document.getElementById('cashFlowAssetsChart');
  const dataUrl = (ctx1 && ctx1.dataset) ? ctx1.dataset.apiUrl : '';
  const auditBtn = document.getElementById('cashFlowAuditBtn');
  const auditUrl = (auditBtn && auditBtn.dataset) ? auditBtn.dataset.url : '';
  let flowChart = null;

  function createFlowChart(){
    if(!ctx1) return;
    flowChart = new Chart(ctx1, {
      plugins: [],
      data:{
        labels: [],
        datasets:[
          {label:'Income', type:'bar', stack:'cash', backgroundColor:'#28a745', data:[]},
          {label:'Expenses', type:'bar', stack:'cash', backgroundColor:'#dc3545', data:[]},
          {label:'Liquid', type:'line', yAxisID:'y2', borderWidth:2, tension:0.3, borderColor:'#ffc107', data:[]},
          {label:'Asset', type:'line', yAxisID:'y2', borderWidth:2, borderDash:[6,3], borderColor:'#17a2b8', data:[]}
        ]
      },
      options:{
        responsive:true,
        interaction:{mode:'index', intersect:false},
        scales:{
          y:{ stacked:true, beginAtZero:true },
          y2:{ position:'right', grid:{drawOnChartArea:false} }
        },
        plugins:{
          tooltip:{ callbacks:{ label:ctx=>`${ctx.dataset.label}: ${formatPeso(ctx.parsed.y)}` } }
        }
      }
    });
    const verticalLine = {
      id:'vline',
      afterDraw(chart){
        if(chart.tooltip?._active && chart.tooltip._active.length){
          const ctx = chart.ctx;
          const x = chart.tooltip._active[0].element.x;
          const topY = chart.scales.y.top;
          const bottomY = chart.scales.y.bottom;
          ctx.save();
          ctx.beginPath();
          ctx.moveTo(x, topY);
          ctx.lineTo(x, bottomY);
          ctx.strokeStyle = 'rgba(0,0,0,0.1)';
          ctx.stroke();
          ctx.restore();
        }
      }
    };
    flowChart.config.plugins = flowChart.config.plugins || [];
    if(!Array.isArray(flowChart.config.plugins)) flowChart.config.plugins = [];
    flowChart.config.plugins.push(verticalLine);
  }

  // ---- Analytics: categories + entities ----
  const analyticsCanvas = document.getElementById('analyticsChart');
  const analyticsUrl = (analyticsCanvas && analyticsCanvas.dataset) ? analyticsCanvas.dataset.apiUrl : '';
  const noDataTop = document.getElementById('topNoDataMsg');
  const entCheckboxes = () => Array.from(document.querySelectorAll('.entity-option'));
  const catCheckboxes = () => Array.from(document.querySelectorAll('.category-option'));
  const getSelectedEntities = () => entCheckboxes().filter(cb=>cb.checked).map(cb=>cb.value);
  const getSelectedCategories = () => catCheckboxes().filter(cb=>cb.checked).map(cb=>cb.value);
  function updateDropdownLabels(){
    const entBtn = document.getElementById('entitiesDropdownBtn');
    const catBtn = document.getElementById('categoriesDropdownBtn');
    const entSel = getSelectedEntities();
    const catSel = getSelectedCategories();
    if(entBtn){
      entBtn.textContent = entSel.length ? `${entSel.length} selected` : 'All entities';
    }
    if(catBtn){
      catBtn.textContent = catSel.length ? `${catSel.length} selected` : 'All categories';
    }
  }
  const labelPlugin = {
    id:'barLabel',
    afterDatasetsDraw(chart){
      const {ctx} = chart;
      const ds = chart.getDatasetMeta(0);
      ds.data.forEach((bar,i)=>{
        const val = chart.data.datasets[0].data[i];
        if(val!==null){
          ctx.save();
          ctx.fillStyle='#fff';
          ctx.textAlign='right';
          ctx.textBaseline='middle';
          ctx.font='12px sans-serif';
          ctx.fillText(formatPeso(val), bar.x-4, bar.y);
          ctx.restore();
        }
      });
    }
  };

  // Unified analytics chart
  let analyticsChart = null;
  function renderAnalytics(payload){
    if(!analyticsCanvas) return;
    if(analyticsChart){ analyticsChart.destroy(); analyticsChart = null; }
    const empty = !payload || !Array.isArray(payload.labels) || payload.labels.length === 0 || !Array.isArray(payload.series) || payload.series.length === 0;
    if(empty){
      noDataTop?.classList.remove('d-none');
      analyticsCanvas.classList.add('invisible');
      return;
    }
    noDataTop?.classList.add('d-none');
    analyticsCanvas.classList.remove('invisible');
    const palette = {
      'Income': 'rgba(25,135,84,0.7)',
      'Expenses': 'rgba(220,53,69,0.7)'
    };
    analyticsChart = new Chart(analyticsCanvas, {
      type:'bar',
      data:{
        labels: payload.labels,
        datasets: (payload.series || []).map(s => ({
          label: s.name,
          backgroundColor: palette[s.name] || 'rgba(13,110,253,0.6)',
          data: (s.data || []).map(Number)
        }))
      },
      options:{
        responsive:true,
        scales:{ y:{ beginAtZero:true } },
        interaction:{ mode:'index', intersect:false },
        plugins:{ tooltip:{ callbacks:{ label:ctx=>`${ctx.dataset.label}: ${formatPeso(ctx.parsed.y)}` } } }
      }
    });
  }

  const entitySel = document.getElementById('entitySelect');
  const cashStart = document.getElementById('cashStart');
  const cashEnd = document.getElementById('cashEnd');
  const spinner = document.getElementById('chartSpinner');
  const noData = document.getElementById('noDataMsg');
  const cache = {};
  let debounceId = null;
  let debounceTopId = null;

  async function fetchData(ent, start, end){
    const key = `${ent}|${start}|${end}`;
    if(cache[key]) return cache[key];
    spinner.classList.remove('d-none');
    try{
      const params = new URLSearchParams();
      params.set('entity_id', ent);
      if(start) params.set('start', start);
      if(end) params.set('end', end);
      const resp = await fetch(`${dataUrl}?${params.toString()}`, {credentials:'same-origin'});
      if(resp.ok){
        const data = await resp.json();
        cache[key] = data;
        return data;
      }
    }catch(err){
      console.error(err);
    }finally{
      spinner.classList.add('d-none');
    }
    return {labels:[], datasets:{income:[], expenses:[], liquid:[], asset:[]}};
  }

    // Map dataset labels to API keys. Extend this map when a new dataset is
  // introduced so the chart picks up the correct values from the payload.
  const keyMap = {
    'Income': 'income',
    'Expenses': 'expenses',
    'Liquid': 'liquid',
    'Asset': 'asset'
  };

  function isEmptyPayload(payload){
    if(!payload.labels || payload.labels.length === 0) return true;
    if(!payload.datasets) return true;
    return Object.values(payload.datasets).every(arr => {
      if(!Array.isArray(arr)) return true;
      return arr.every(v => Number(v) === 0);
    });
  }

  // Update chart data in place using the mapping above. Any dataset coming from
  // the API that does not exist in the chart will be logged in the console.
  function refreshChart(payload){
    if(isEmptyPayload(payload)){
      ctx1.classList.add('invisible');
      noData.classList.remove('d-none');
      if(flowChart){ flowChart.destroy(); flowChart = null; }
      return;
    }
    noData.classList.add('d-none');
    ctx1.classList.remove('invisible');
    if(!flowChart) createFlowChart();
    flowChart.data.labels = payload.labels || [];
    const usedKeys = new Set();
    flowChart.data.datasets.forEach(ds => {
      const apiKey = keyMap[ds.label];
      if(apiKey && payload.datasets && Array.isArray(payload.datasets[apiKey])){
        usedKeys.add(apiKey);
        const values = payload.datasets[apiKey].map(Number);
        ds.data = ds.label === 'Expenses' ? values.map(v => -v) : values;
      } else {
        console.warn(`Missing data for dataset '${ds.label}'`);
        ds.data = Array(flowChart.data.labels.length).fill(0);
      }
    });
    // Warn about extra keys returned by the API that the chart has no dataset for
    if(payload.datasets){
      Object.keys(payload.datasets).forEach(k => {
        if(!usedKeys.has(k)) console.warn(`API dataset '${k}' has no matching chart dataset`);
      });
    }

    flowChart.update();
  }

  async function loadData(){
    if(!dataUrl){
      if(!bootstrapFromServer()) return; // nothing to draw
      return;
    }
    const data = await fetchData(entitySel.value, cashStart.value, cashEnd.value);
    refreshChart(data);
  }

  // If the API call doesn't happen (e.g., blocked by browser or offline),
  // draw using server-provided monthly summary embedded in the page.
  function bootstrapFromServer(){
    try{
      const el = document.getElementById('initial-flow');
      if(!el) return false;
      const summary = JSON.parse(el.textContent || '[]');
      if(!Array.isArray(summary) || summary.length === 0) return false;
      const payload = {
        labels: summary.map(r=>r.month),
        datasets: {
          income: summary.map(r=>Number(r.income || 0)),
          expenses: summary.map(r=>Number(r.expenses || 0)),
          liquid: summary.map(r=>Number(r.liquid || 0)),
          asset: summary.map(r=>Number(r.non_liquid || 0)),
        }
      };
      refreshChart(payload);
      return true;
    }catch(e){
      console.error(e);
      return false;
    }
  }

  function debouncedLoad(){
    clearTimeout(debounceId);
    debounceId = setTimeout(loadData, 200);
  }

  function updateAuditLink(){
    try{
      if(!auditBtn || !auditUrl) return;
      const params = new URLSearchParams();
      const entVal = entitySel?.value;
      if(entVal && entVal !== 'overall') params.set('entity_id', entVal);
      if(cashStart?.value) params.set('start', cashStart.value);
      if(cashEnd?.value) params.set('end', cashEnd.value);
      auditBtn.href = `${auditUrl}?${params.toString()}`;
    }catch(e){ console.error(e); }
  }

  // legacy helper kept to avoid errors if referenced; returns empty payload
  async function fetchTopData(){ return {labels:[], amounts:[], types:[]}; }

  // legacy category/entity fetchers no longer used

  async function loadAnalytics(){
    const payload = await (async () => {
      if(analyticsUrl){
        const ids = getSelectedEntities().join(',');
        const cats = getSelectedCategories().join(',');
        const dim = cats ? 'categories' : 'entities';
        const params = new URLSearchParams();
        params.set('dimension', dim);
        if(ids) params.set('entities', ids);
        if(cats) params.set('categories', cats);
        if(topStart?.value) params.set('start', topStart.value);
        if(topEnd?.value) params.set('end', topEnd.value);
        const resp = await fetch(`${analyticsUrl}?${params.toString()}`, {credentials:'same-origin'});
        if(resp.ok) return await resp.json();
      }
      return {labels:[], series:[]};
    })();
    renderAnalytics(payload);
  }

  // Debounced analytics reload
  function debouncedTop(){
    clearTimeout(debounceTopId);
    debounceTopId = setTimeout(loadAnalytics, 200);
  }

  entitySel?.addEventListener('change', ()=>{ updateQuery(); updateAuditLink(); debouncedLoad(); });
  cashStart?.addEventListener('change', ()=>{ updateQuery(); updateAuditLink(); debouncedLoad(); });
  cashEnd?.addEventListener('change', ()=>{ updateQuery(); updateAuditLink(); debouncedLoad(); });
  const topStart = document.getElementById('topStart');
  const topEnd = document.getElementById('topEnd');

  const urlParams = new URLSearchParams(location.search);
  function applyInitialFilters(){
    const entParam = urlParams.get('entities');
    if(entParam){
      const ids = new Set(entParam.split(','));
      entCheckboxes().forEach(cb=>{ cb.checked = ids.has(cb.value); });
    }
    const catsParam = urlParams.get('categories');
    if(catsParam){
      const names = new Set(catsParam.split(','));
      catCheckboxes().forEach(cb=>{ cb.checked = names.has(cb.value); });
    }
    const startParam = urlParams.get('start');
    const endParam = urlParams.get('end');
    if(startParam){
      cashStart.value = startParam;
      topStart.value = startParam;
    }
    if(endParam){
      cashEnd.value = endParam;
      topEnd.value = endParam;
    }
  }

  function updateQuery(){
    const ids = getSelectedEntities().join(',');
    if(ids) urlParams.set('entities', ids); else urlParams.delete('entities');
    const cats = getSelectedCategories().join(',');
    if(cats) urlParams.set('categories', cats); else urlParams.delete('categories');
    if(cashStart.value) urlParams.set('start', cashStart.value);
    if(cashEnd.value) urlParams.set('end', cashEnd.value);
    history.replaceState(null, '', `${location.pathname}?${urlParams.toString()}`);
  }

  entCheckboxes().forEach(cb=>cb.addEventListener('change', ()=>{ updateDropdownLabels(); updateQuery(); loadAnalytics(); }));
  catCheckboxes().forEach(cb=>cb.addEventListener('change', ()=>{ updateDropdownLabels(); updateQuery(); loadAnalytics(); }));
  topStart?.addEventListener('change', ()=>{ updateQuery(); loadAnalytics(); });
  topEnd?.addEventListener('change', ()=>{ updateQuery(); loadAnalytics(); });

  const clearCashBtn = document.getElementById('clearCashFilter');
  if(clearCashBtn){
    clearCashBtn.addEventListener('click', () => {
      entitySel.value = entitySel.dataset.default || 'overall';
      cashStart.value = cashStart.dataset.default || '';
      cashEnd.value = cashEnd.dataset.default || '';
      updateQuery();
      loadData();
    });
  }

  const clearTopBtn = document.getElementById('clearTopFilter');
  if(clearTopBtn){
    clearTopBtn.addEventListener('click', () => {
      entCheckboxes().forEach(cb=>cb.checked=false);
      catCheckboxes().forEach(cb=>cb.checked=false);
      updateDropdownLabels();
      topStart.value = topStart.dataset.default || '';
      topEnd.value = topEnd.dataset.default || '';
      updateQuery();
      loadAnalytics();
    });
  }

  applyInitialFilters();
  updateAuditLink();

  // Select all/none helpers for multi-selects
  const btnSelAllEnt = document.getElementById('selectAllEntities');
  const btnClrEnt = document.getElementById('clearEntities');
  const btnSelAllCat = document.getElementById('selectAllCategories');
  const btnClrCat = document.getElementById('clearCategories');
  btnSelAllEnt?.addEventListener('click', ()=>{ entCheckboxes().forEach(cb=>cb.checked=true); updateDropdownLabels(); updateQuery(); loadAnalytics(); });
  btnClrEnt?.addEventListener('click', ()=>{ entCheckboxes().forEach(cb=>cb.checked=false); updateDropdownLabels(); updateQuery(); loadAnalytics(); });
  btnSelAllCat?.addEventListener('click', ()=>{ catCheckboxes().forEach(cb=>cb.checked=true); updateDropdownLabels(); updateQuery(); loadAnalytics(); });
  btnClrCat?.addEventListener('click', ()=>{ catCheckboxes().forEach(cb=>cb.checked=false); updateDropdownLabels(); updateQuery(); loadAnalytics(); });

  // Try to render immediately with server data; if not available, fetch.
  if(!bootstrapFromServer()){
    loadData();
  }
  updateDropdownLabels();
  loadAnalytics();
});
