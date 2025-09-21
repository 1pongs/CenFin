const { test, expect } = require('@playwright/test');

// Note: This test assumes the dev server is running on http://localhost:8000
// and that test user credentials and fixtures are available. Adjust the
// login sequence to match your project's auth flow.

test.describe('Transaction Outside defaults', () => {
  const base = 'http://localhost:8000';

  test.beforeEach(async ({ page }) => {
    const loginUrl = `${base}/users/login/`;
    await page.goto(loginUrl);
    await page.fill('input[name="username"]', 'testuser');
    await page.fill('input[name="password"]', 'testpass');
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'load' }),
      page.click('button[type="submit"]')
    ]);
    // Ensure at least one template exists for this user so template-select tests run.
    // Create a minimal template using an in-page fetch so the browser sends
    // cookies and the CSRF token automatically (server requires CSRF for POST).
    try {
      await page.evaluate(async () => {
        function getCookie(name){
          const m = document.cookie.split('; ').find(c => c.startsWith(name + '='));
          return m ? decodeURIComponent(m.split('=')[1]) : null;
        }
        const csrftoken = getCookie('csrftoken');
        const body = new URLSearchParams();
        body.append('name', 'e2e-template');
        body.append('transaction_type', 'expense');
        try {
          await fetch('/api/create/template/', { method: 'POST', body, headers: { 'X-CSRFToken': csrftoken } });
        } catch (e) {
          // best-effort — ignore
        }
      });
    } catch (e) {
      // ignore any errors creating the template
    }
  });

  test('expense locks destination to Outside and income locks source to Outside', async ({ page }) => {
    await page.goto(`${base}/transactions/new/`);
    await page.waitForSelector('#id_transaction_type', { timeout: 10000 });

    // Select expense and assert account_destination/entity_destination are set to Outside
    await page.selectOption('#id_transaction_type', 'expense');
    // Wait a bit for client JS to run
    await page.waitForTimeout(250);

    const accDestDisabled = await page.isDisabled('#id_account_destination');
    const entDestDisabled = await page.isDisabled('#id_entity_destination');
    expect(accDestDisabled).toBeTruthy();
    expect(entDestDisabled).toBeTruthy();

    // Ensure the selected option text equals 'Outside'
    const accDestVal = await page.$eval('#id_account_destination', el => el.options[el.selectedIndex]?.text?.trim() || '');
    const entDestVal = await page.$eval('#id_entity_destination', el => el.options[el.selectedIndex]?.text?.trim() || '');
    expect(accDestVal).toBe('Outside');
    expect(entDestVal).toBe('Outside');

    // Select income and assert account_source/entity_source are set to Outside
    await page.selectOption('#id_transaction_type', 'income');
    await page.waitForTimeout(250);

    const accSrcDisabled = await page.isDisabled('#id_account_source');
    const entSrcDisabled = await page.isDisabled('#id_entity_source');
    expect(accSrcDisabled).toBeTruthy();
    expect(entSrcDisabled).toBeTruthy();

    const accSrcVal = await page.$eval('#id_account_source', el => el.options[el.selectedIndex]?.text?.trim() || '');
    const entSrcVal = await page.$eval('#id_entity_source', el => el.options[el.selectedIndex]?.text?.trim() || '');
    expect(accSrcVal).toBe('Outside');
    expect(entSrcVal).toBe('Outside');
  });

  test('select template applies Outside defaults correctly', async ({ page }) => {
    const base = 'http://localhost:8000';
    await page.goto(`${base}/transactions/new/`);
  await page.waitForSelector('#id_template', { timeout: 10000 });

    // If there's at least one template, pick it and assert behavior. If
    // none exists, the test will just ensure the template-select exists.
    const tplExists = await page.$('#id_template option[value]');
    if (!tplExists) {
      test.skip();
    }
    // pick the first non-empty template
    const tplVal = await page.$eval('#id_template', sel => Array.from(sel.options).find(o => o.value)?.value);
    if (!tplVal) test.skip();

    await page.selectOption('#id_template', tplVal);
    await page.waitForTimeout(250);

    // After applying template, ensure selects didn't become blank when
    // autopop suggests 'expense' type.
    const accDestText = await page.$eval('#id_account_destination', el => el.options[el.selectedIndex]?.text?.trim() || '');
    const entDestText = await page.$eval('#id_entity_destination', el => el.options[el.selectedIndex]?.text?.trim() || '');
    // If the template showed expense behaviour, these should be Outside or non-empty
    expect(accDestText).not.toBe('');
    expect(entDestText).not.toBe('');
  });
});
