document.addEventListener('DOMContentLoaded', () => {
  const bigTicketsEl = document.getElementById('top-big-data');
  const bigTickets = bigTicketsEl ? JSON.parse(bigTicketsEl.textContent || '[]') : [];
  
  function formatPeso(val){
    return `\u20B1${Number(val).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
  }

  const ctx1 = document.getElementById('cashFlowAssetsChart');
  const dataUrl = (ctx1 && ctx1.dataset) ? ctx1.dataset.apiUrl : '';
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
  const catCanvas = document.getElementById('categoryChart');
  const entCanvas = document.getElementById('entityChart');
  const topEl = document.getElementById('topEntriesChart');
  const topUrl = (topEl && topEl.dataset) ? topEl.dataset.apiUrl : '';
  const noDataTop = document.getElementById('topNoDataMsg');
  const catUrl = (catCanvas && catCanvas.dataset) ? catCanvas.dataset.apiUrl : '';
  const entUrl = (entCanvas && entCanvas.dataset) ? entCanvas.dataset.apiUrl : '';
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

  // Category donut
  let catChart = null;
  function renderCategoryChart(rows){
    if(!catCanvas) return;
    if(catChart) { catChart.destroy(); catChart = null; }
    if(!rows || !rows.length){ noDataTop.classList.remove('d-none'); catCanvas.classList.add('invisible'); return; }
    noDataTop.classList.add('d-none'); catCanvas.classList.remove('invisible');
    catChart = new Chart(catCanvas, {
      type:'doughnut',
      data:{labels: rows.map(r=>r.name), datasets:[{data: rows.map(r=>r.total)}]},
      options:{responsive:true, plugins:{legend:{position:'bottom'}, tooltip:{callbacks:{label:ctx=>`${ctx.label}: ${formatPeso(ctx.parsed)}`}}}}
    });
  }

  // Entity bars
  let entChart = null;
  function renderEntityChart(rows){
    if(!entCanvas) return;
    if(entChart) { entChart.destroy(); entChart = null; }
    if(!rows || !rows.length){ noDataTop.classList.remove('d-none'); entCanvas.classList.add('invisible'); return; }
    noDataTop.classList.add('d-none'); entCanvas.classList.remove('invisible');
    entChart = new Chart(entCanvas, {
      type:'bar',
      data:{
        labels: rows.map(r=>r.entity),
        datasets:[
          {label:'Income', backgroundColor:'rgba(25,135,84,0.6)', data: rows.map(r=>r.income)},
          {label:'Expenses', backgroundColor:'rgba(220,53,69,0.6)', data: rows.map(r=>r.expenses)},
          {label:'Capital', backgroundColor:'rgba(108,117,125,0.6)', data: rows.map(r=>r.capital)}
        ]
      },
      options:{responsive:true, scales:{y:{beginAtZero:true}}, interaction:{mode:'index', intersect:false}}
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

  async function fetchTopData(){
    const ids = [...entitySelTop.selectedOptions].map(o=>o.value).join(',');
    const params = new URLSearchParams();
    if(ids) params.set('entities', ids);
    if(txnTypeSel.value) params.set('txn_type', txnTypeSel.value);
    if(topStart.value) params.set('start', topStart.value);
    if(topEnd.value) params.set('end', topEnd.value);
    try{
      const resp = await fetch(`${topUrl}?${params.toString()}`, {credentials:'same-origin'});
      if(resp.ok) return await resp.json();
    }catch(err){
      console.error(err);
    }
    return {labels:[], amounts:[], types:[]};
  }

  async function fetchCategoryData(){
    const ids = [...entitySelTop.selectedOptions].map(o=>o.value).join(',');
    const params = new URLSearchParams();
    params.set('type', txnTypeSel.value === 'income' ? 'income' : 'expense');
    if(ids) params.set('entities', ids);
    if(topStart.value) params.set('start', topStart.value);
    if(topEnd.value) params.set('end', topEnd.value);
    const resp = await fetch(`${catUrl}?${params.toString()}`, {credentials:'same-origin'});
    if(resp.ok) return await resp.json();
    return [];
  }

  async function fetchEntityData(){
    const ids = [...entitySelTop.selectedOptions].map(o=>o.value).join(',');
    const params = new URLSearchParams();
    if(ids) params.set('entities', ids);
    if(topStart.value) params.set('start', topStart.value);
    if(topEnd.value) params.set('end', topEnd.value);
    const resp = await fetch(`${entUrl}?${params.toString()}`, {credentials:'same-origin'});
    if(resp.ok) return await resp.json();
    return [];
  }

  async function loadAnalytics(){
    if(document.getElementById('view-cats') && !document.getElementById('view-cats').classList.contains('d-none')){
      const rows = await fetchCategoryData();
      renderCategoryChart(rows);
    } else if(document.getElementById('view-ents')){
      const rows = await fetchEntityData();
      renderEntityChart(rows);
    }
  }

  function debouncedTop(){
    clearTimeout(debounceTopId);
    debounceTopId = setTimeout(loadTop, 200);
  }

  entitySel?.addEventListener('change', ()=>{ updateQuery(); debouncedLoad(); });
  cashStart?.addEventListener('change', ()=>{ updateQuery(); debouncedLoad(); });
  cashEnd?.addEventListener('change', ()=>{ updateQuery(); debouncedLoad(); });
  const entitySelTop = document.getElementById('entitiesFilter');
  const txnTypeSel = document.getElementById('txnTypeFilter');
  const topStart = document.getElementById('topStart');
  const topEnd = document.getElementById('topEnd');

  const urlParams = new URLSearchParams(location.search);
  function applyInitialFilters(){
    const entParam = urlParams.get('entities');
    if(entParam){
      const ids = entParam.split(',');
      [...entitySelTop.options].forEach(o=>{ o.selected = ids.includes(o.value); });
    }
    const tx = urlParams.get('txn_type');
    if(tx){
      txnTypeSel.value = tx;
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
    const ids = [...entitySelTop.selectedOptions].map(o=>o.value).join(',');
    if(ids) urlParams.set('entities', ids); else urlParams.delete('entities');
    urlParams.set('txn_type', txnTypeSel.value);
    if(cashStart.value) urlParams.set('start', cashStart.value);
    if(cashEnd.value) urlParams.set('end', cashEnd.value);
    history.replaceState(null, '', `${location.pathname}?${urlParams.toString()}`);
  }

  entitySelTop?.addEventListener('change', ()=>{ updateQuery(); loadAnalytics(); });
  txnTypeSel?.addEventListener('change', ()=>{ updateQuery(); loadAnalytics(); });
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
      txnTypeSel.value = txnTypeSel.dataset.default || 'all';
      [...entitySelTop.options].forEach(o => { o.selected = false; });
      topStart.value = topStart.dataset.default || '';
      topEnd.value = topEnd.dataset.default || '';
      updateQuery();
      loadTop();
    });
  }

  applyInitialFilters();

  // Tab switching for analytics card
  const tabCats = document.getElementById('tab-cats');
  const tabEnts = document.getElementById('tab-ents');
  function switchTab(target){
    const vc = document.getElementById('view-cats');
    const ve = document.getElementById('view-ents');
    if(target==='cats'){
      vc.classList.remove('d-none');
      ve.classList.add('d-none');
      tabCats.classList.add('active');
      tabEnts.classList.remove('active');
    } else {
      vc.classList.add('d-none');
      ve.classList.remove('d-none');
      tabCats.classList.remove('active');
      tabEnts.classList.add('active');
    }
    loadAnalytics();
  }
  tabCats?.addEventListener('click', (e)=>{ e.preventDefault(); switchTab('cats'); });
  tabEnts?.addEventListener('click', (e)=>{ e.preventDefault(); switchTab('ents'); });

  // Try to render immediately with server data; if not available, fetch.
  if(!bootstrapFromServer()){
    loadData();
  }
  switchTab('cats');
});
