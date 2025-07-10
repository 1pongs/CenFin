const fs = require('fs');
const path = require('path');

describe('exchange rate form', () => {
  let container;
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="toast-container"></div>
      <select id="id_source"><option value="">---</option><option value="FRANKFURTER">F</option></select>
      <select id="id_currency_from"></select>
      <select id="id_currency_to"></select>
      <button name="save"></button>`;
    container = document.querySelector('.toast-container');
    global.bootstrap = {Toast:{getOrCreateInstance: () => ({show: jest.fn()})}};
    jest.resetModules();
  });

  function loadScript(){
    const script = fs.readFileSync(path.join(__dirname,'../cenfin_proj/static/js/exchange_rate_form.js'),'utf8');
    eval(script);
    document.dispatchEvent(new Event('DOMContentLoaded'));
  }

  test('shows banner on 502 and clears on success', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ok:false,status:502,json:()=>Promise.resolve({})}));
    loadScript();
    document.getElementById('id_source').value='FRANKFURTER';
    document.getElementById('id_source').dispatchEvent(new Event('change'));
    await Promise.resolve();
    await Promise.resolve();
    expect(container.textContent).toContain('Error loading currencies');

    global.fetch = jest.fn(() => Promise.resolve({ok:true,json:()=>Promise.resolve({USD:'US Dollar'})}));
    document.getElementById('id_source').dispatchEvent(new Event('change'));
    await Promise.resolve();
    await Promise.resolve();
    expect(container.textContent).not.toContain('Error loading currencies');
  });
});