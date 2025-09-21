const { test, expect } = require('@playwright/test');

// This test spins up a small HTML fixture mirroring the transaction form
// and verifies that selecting a template populates fields and Tagify tags.

// We don't run your Django server here; instead we load a static HTML page
// that includes the same JS behavior. For full end-to-end against the app
// you'd launch the dev server and navigate to the real URL.

const fs = require('fs');
const path = require('path');

const fixtureHtml = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <script src="https://cdn.jsdelivr.net/npm/@yaireo/tagify"></script>
</head>
<body>
  <select id="id_template">
    <option value="">(none)</option>
    <option value="1">T1</option>
  </select>
  <input id="id_description" />
  <select id="id_transaction_type">
    <option value="">--</option>
    <option value="expense">Expense</option>
  </select>
  <select id="id_account_source"><option value="10">Cash-on-hand</option></select>
  <select id="id_entity_source"><option value="20">Account</option></select>
  <input id="id_amount" />
  <input id="id_category_names" />

  <script>
    // Simulate templatesData and the template change handler logic
    const templatesData = { '1': { 'description': 'Tahop', 'transaction_type': 'expense', 'amount': '15', 'categories': ['Tahop'] } };
    const templateSelect = document.getElementById('id_template');
    templateSelect.addEventListener('change', function() {
      const tplId = this.value;
      const defaults = templatesData[tplId] || {};
      if (defaults.description !== undefined) document.getElementById('id_description').value = defaults.description;
      if (defaults.transaction_type !== undefined) document.getElementById('id_transaction_type').value = defaults.transaction_type;
      if (defaults.amount !== undefined) document.getElementById('id_amount').value = defaults.amount;
      if (window.categoryTagify && defaults.categories) {
        window.categoryTagify.removeAllTags();
        window.categoryTagify.addTags(defaults.categories);
      }
      ['id_transaction_type','id_account_source','id_entity_source'].forEach(id=>{ const el=document.getElementById(id); if(el) el.dispatchEvent(new Event('change',{bubbles:true}));});
    });

    // Initialize Tagify and expose global
    const input = document.getElementById('id_category_names');
    const t = new Tagify(input);
    window.categoryTagify = t;
  </script>
</body>
</html>`;

const fixturePath = path.join(__dirname, 'fixture.html');

test.beforeAll(() => {
  fs.writeFileSync(fixturePath, fixtureHtml);
});

test.afterAll(() => {
  try { fs.unlinkSync(fixturePath); } catch (e) {}
});

test('template selection populates category tags', async ({ page }) => {
  const fileUrl = 'file://' + fixturePath;
  await page.goto(fileUrl);
  await page.selectOption('#id_template', '1');
  // Wait for Tagify to add tags
  await page.waitForTimeout(200);
  const tags = await page.$$eval('.tagify__tag', els => els.map(e => e.textContent.trim()));
  expect(tags.some(t => t.includes('Tahop'))).toBeTruthy();
});
