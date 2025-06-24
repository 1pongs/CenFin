document.addEventListener('DOMContentLoaded', () => {
  const bigTickets = JSON.parse(document.getElementById('top-big-data').textContent);
  
  function formatPeso(val){
    return `\u20B1${Number(val).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
  }

  const ctx1 = document.getElementById('cashFlowAssetsChart');
  const dataUrl = ctx1.dataset.apiUrl;
  const flowChart = new Chart(ctx1, {
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

  const ctx2 = document.getElementById('topEntriesChart');
  const topUrl = ctx2.dataset.apiUrl;
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

  const ticketChart = new Chart(ctx2, {
    type:'bar',
    data:{
      labels: bigTickets.map(r => r.category),
      datasets:[{
        data: bigTickets.map(r => r.amount),
        backgroundColor: bigTickets.map(r => {
          if(r.type==='income') return 'rgba(25,135,84,0.7)';
          if(r.type==='expense') return 'rgba(220,53,69,0.7)';
          if(r.type==='asset') return 'rgba(23,162,184,0.7)';
          return 'gray';
        })
      }]
    },
    options:{
      responsive:true,
      indexAxis:'y',
      scales:{ x:{beginAtZero:true} },
      plugins:{
        legend:{display:false},
        tooltip:{ callbacks:{ label:ctx=>`${ctx.label}: ${formatPeso(ctx.parsed.x)}` } }
      }
    },
    plugins:[labelPlugin]
  });

  const entitySel = document.getElementById('entitySelect');
  const monthSel = document.getElementById('monthSelect');
  const spinner = document.getElementById('chartSpinner');
  const noData = document.getElementById('noDataMsg');
  const cache = {};
  let debounceId = null;
  let debounceTopId = null;

  async function fetchData(ent, months){
    const key = `${ent}|${months}`;
    if(cache[key]) return cache[key];
    spinner.classList.remove('d-none');
    try{
      const resp = await fetch(`${dataUrl}?entity_id=${ent}&months=${months}`, {credentials:'same-origin'});
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

  // Update chart data in place using the mapping above. Any dataset coming from
  // the API that does not exist in the chart will be logged in the console.
  function refreshChart(chart, payload){
    chart.data.labels = payload.labels || [];
    const usedKeys = new Set();
    chart.data.datasets.forEach(ds => {
      const apiKey = keyMap[ds.label];
      if(apiKey && payload.datasets && Array.isArray(payload.datasets[apiKey])){
        usedKeys.add(apiKey);
        const values = payload.datasets[apiKey].map(Number);
        ds.data = ds.label === 'Expenses' ? values.map(v => -v) : values;
      } else {
        console.warn(`Missing data for dataset '${ds.label}'`);
        ds.data = Array(chart.data.labels.length).fill(0);
      }
    });
    // Warn about extra keys returned by the API that the chart has no dataset for
    if(payload.datasets){
      Object.keys(payload.datasets).forEach(k => {
        if(!usedKeys.has(k)) console.warn(`API dataset '${k}' has no matching chart dataset`);
      });
    }

    if(chart.data.labels.length === 0){
      noData.classList.remove('d-none');
    }else{
      noData.classList.add('d-none');
    }
    chart.update();
  }

  async function loadData(){
    const data = await fetchData(entitySel.value, monthSel.value);
    refreshChart(flowChart, data);
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
    try{
      const resp = await fetch(`${topUrl}?${params.toString()}`, {credentials:'same-origin'});
      if(resp.ok) return await resp.json();
    }catch(err){
      console.error(err);
    }
    return {labels:[], amounts:[], types:[]};
  }

  function refreshTop10(chart, payload){
    chart.data.labels = payload.labels || [];
    const amounts = (payload.amounts || []).map(Number);
    chart.data.datasets[0].data = amounts;
    chart.data.datasets[0].backgroundColor = (payload.types || []).map(t=>{
      if(t==='income') return 'rgba(40,167,69,0.7)';
      if(t==='expense') return 'rgba(220,53,69,0.7)';
      if(t==='asset') return 'rgba(23,162,184,0.7)';
      return 'gray';
    });
    chart.update();
  }

  async function loadTop(){
    const data = await fetchTopData();
    refreshTop10(ticketChart, data);
  }

  function debouncedTop(){
    clearTimeout(debounceTopId);
    debounceTopId = setTimeout(loadTop, 200);
  }

  entitySel.addEventListener('change', debouncedLoad);
  monthSel.addEventListener('change', debouncedLoad);
  const entitySelTop = document.getElementById('entitiesFilter');
  const txnTypeSel = document.getElementById('txnTypeFilter');

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
  }

  function updateQuery(){
    const ids = [...entitySelTop.selectedOptions].map(o=>o.value).join(',');
    if(ids) urlParams.set('entities', ids); else urlParams.delete('entities');
    urlParams.set('txn_type', txnTypeSel.value);
    history.replaceState(null, '', `${location.pathname}?${urlParams.toString()}`);
  }

  entitySelTop.addEventListener('change', ()=>{ updateQuery(); debouncedTop(); });
  txnTypeSel.addEventListener('change', ()=>{ updateQuery(); debouncedTop(); });

  applyInitialFilters();

  loadData();
  loadTop();
});