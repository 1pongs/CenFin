document.addEventListener('DOMContentLoaded', () => {
  const bigTickets = JSON.parse(document.getElementById('top-big-data').textContent);
  
  function formatPeso(val){
    return `\u20B1${Number(val).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
  }

  const ctx1 = document.getElementById('cashFlowAssetsChart');
  const dataUrl = ctx1.dataset.apiUrl;
  const flowChart = new Chart(ctx1, {
    data:{
      labels: [],
      datasets:[
        {label:'Income', type:'bar', stack:'flow', backgroundColor:'rgba(25,135,84,0.7)', data:[]},
        {label:'Expenses', type:'bar', stack:'flow', backgroundColor:'rgba(220,53,69,0.7)', data:[]},
        {label:'Liquid', type:'line', yAxisID:'y1', borderColor:'orange', backgroundColor:'orange', data:[]},
        {label:'Non-liquid', type:'line', yAxisID:'y1', borderColor:'blue', backgroundColor:'blue', data:[]},
        {label:'Net Worth', type:'line', yAxisID:'y1', borderColor:'teal', backgroundColor:'teal', data:[]}
      ]
    },
    options:{
      responsive:true,
      interaction:{mode:'index', intersect:false},
      scales:{
        x:{stacked:true},
        y:{stacked:true, beginAtZero:true},
        y1:{position:'right', beginAtZero:true, grid:{drawOnChartArea:false}}
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
  flowChart.config.plugins.push(verticalLine);

  const ctx2 = document.getElementById('topEntriesChart');
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
          if(r.type==='asset') return 'rgba(13,110,253,0.7)';
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
    return {labels:[], datasets:{income:[], expenses:[], liquid:[], nonliquid:[], net_worth:[]}};
  }

  function updateChart(payload){
    const ds = payload.datasets || {};
    flowChart.data.labels = payload.labels || [];
    flowChart.data.datasets[0].data = ds.income || [];
    flowChart.data.datasets[1].data = (ds.expenses || []).map(v => -v);
    flowChart.data.datasets[2].data = ds.liquid || [];
    flowChart.data.datasets[3].data = ds.nonliquid || [];
    flowChart.data.datasets[4].data = ds.net_worth || [];
    if(flowChart.data.labels.length === 0){
      noData.classList.remove('d-none');
    }else{
      noData.classList.add('d-none');
    }
    flowChart.update();
  }

  async function loadData(){
    const data = await fetchData(entitySel.value, monthSel.value);
    updateChart(data);
  }

  function debouncedLoad(){
    clearTimeout(debounceId);
    debounceId = setTimeout(loadData, 200);
  }

  entitySel.addEventListener('change', debouncedLoad);
  monthSel.addEventListener('change', debouncedLoad);
  loadData();
});