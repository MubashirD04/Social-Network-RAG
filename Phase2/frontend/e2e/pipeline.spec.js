import { expect, test } from '@playwright/test';
import path from 'node:path';

const FIXTURE = path.join(import.meta.dirname, 'fixtures/chat.txt');
const ALLOWED_HOSTS = ['localhost', 'cdn.jsdelivr.net', 'pypi.org', 'files.pythonhosted.org', 'huggingface.co'];

const isAllowed = (url) => {
  const { hostname, protocol } = new URL(url);
  if (protocol === 'data:' || protocol === 'blob:') return true;
  return ALLOWED_HOSTS.some(host => hostname === host || hostname.endsWith(`.${host}`) || hostname.endsWith('.hf.co'));
};

// Runs the real Pyodide + transformers.js pipeline, so it downloads both.
test('real pipeline: cross-origin isolated, only expected origins, no chat text sent', async ({ page }) => {
  test.setTimeout(300_000);
  const requests = [];
  page.on('request', r => requests.push({ url: r.url(), body: r.postData() }));

  // The bars can pass quickly, so record every value they show.
  await page.addInitScript(() => {
    window.__bars = {};
    setInterval(() => {
      document.querySelectorAll('[role="progressbar"]').forEach(bar => {
        const name = bar.getAttribute('aria-label');
        (window.__bars[name] ??= []).push(Number(bar.getAttribute('aria-valuenow')));
      });
    }, 20);
  });

  await page.goto('/');
  expect(await page.evaluate(() => self.crossOriginIsolated)).toBe(true);

  await page.locator('input[type="file"]').setInputFiles(FIXTURE);
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 280_000 });
  await expect(page.getByLabel('Ask a question about the chat')).toBeVisible({ timeout: 280_000 });

  const bars = await page.evaluate(() => window.__bars);
  console.log('model bar:', [...new Set(bars['Embedding model'])].join(' '));
  console.log('embedding bar:', [...new Set(bars['Message embeddings'])].join(' '));
  expect(Math.max(...bars['Embedding model'])).toBe(100);
  expect(Math.max(...bars['Message embeddings'])).toBe(100);

  await page.getByLabel('Ask a question about the chat').fill('what happened to the coffee machine?');
  await page.keyboard.press('Enter');
  await page.locator('.results-list .result-item').first().click();
  await expect(page.locator('.details-sidebar')).toBeVisible();

  const unexpected = requests.filter(r => !isAllowed(r.url)).map(r => r.url);
  expect(unexpected).toEqual([]);
  const leaked = requests.filter(r => /coffee/i.test(`${r.url} ${r.body ?? ''}`));
  expect(leaked).toEqual([]);
});
