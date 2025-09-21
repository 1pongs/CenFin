// Playwright config for minimal e2e tests
const { devices } = require('@playwright/test');

module.exports = {
  testDir: 'e2e/tests',
  timeout: 30000,
  use: {
    headless: true,
    viewport: { width: 1280, height: 800 },
    actionTimeout: 5000,
    ignoreHTTPSErrors: true,
  },
};