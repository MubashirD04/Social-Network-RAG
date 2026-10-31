import { expect, test } from '@playwright/test';
import { openBrowser, syntheticGraph, uploadFixture, useFakePipeline } from './helpers.js';

const pickFromBrowser = async (page, name) => {
  await openBrowser(page);
  await page.getByRole('button', { name: new RegExp(name) }).first().click();
  await expect(page.locator('.details-sidebar h2')).toHaveText(new RegExp(name));
};

test.describe('graph view', () => {
  test.beforeEach(async ({ page }) => {
    await useFakePipeline(page, syntheticGraph(60), [
      { message_id: '7', sender: 'User 7', content: 'message 7 body', score: 0.9, timestamp: '2026-01-01T00:00:00',
        linked_context: [{ message_id: '9', sender: 'User 9', content: 'message 9 body', timestamp: '2026-01-01T00:00:00' }] },
    ]);
    await page.goto('/');
    await uploadFixture(page);
  });

  test('starts in the overview and expands messages on selection', async ({ page }) => {
    await expect(page.getByRole('button', { name: /expanded message/ })).toHaveCount(0);
    await pickFromBrowser(page, 'User 0');
    await expect(page.getByRole('button', { name: /Hide 6 expanded messages/ })).toBeVisible();
    await expect(page.locator('.connection-summary')).toContainText('confirmed');
    await page.getByRole('button', { name: /Hide 6 expanded/ }).click();
    await expect(page.getByRole('button', { name: /expanded message/ })).toHaveCount(0);
  });

  test('search result and linked context jump to their messages', async ({ page }) => {
    await page.getByLabel('Ask a question about the chat').fill('anything');
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /message 7 body/ }).click();
    await expect(page.locator('.details-sidebar')).toContainText('message 7 body');
    await page.getByRole('button', { name: /message 9 body/ }).click();
    await expect(page.locator('.details-sidebar')).toContainText('message 9 body');
  });

  test('topic slider keeps the selection unless its node goes away', async ({ page }) => {
    await pickFromBrowser(page, 'User 0');
    await page.getByLabel(/Topics shown/).fill('7');
    await expect(page.getByLabel(/Topics shown/)).toBeEnabled();
    await expect(page.locator('.details-sidebar h2')).toHaveText('User 0');
  });

  test('inferred toggle and show-all control work from the keyboard', async ({ page }) => {
    const inferred = page.getByRole('checkbox', { name: /inferred connections/ });
    await inferred.focus();
    await page.keyboard.press('Space');
    await expect(inferred).not.toBeChecked();
    const all = page.getByRole('checkbox', { name: 'Show every message' });
    await all.focus();
    await page.keyboard.press('Space');
    await expect(all).toBeChecked();
  });

  test('node browser filters messages by text', async ({ page }) => {
    await openBrowser(page);
    await page.getByLabel(/Filter people/).fill('message 12 body');
    await expect(page.locator('.node-count')).toHaveText('1 found');
  });

  test('switching to 3D renders WebGL and keeps selection working', async ({ page }) => {
    await page.getByRole('button', { name: '3D', exact: true }).click();
    await expect(page.locator('.view-3d')).toBeVisible();
    await expect.poll(() => page.locator('canvas').evaluate(c => !!c.getContext('webgl2'))).toBe(true);
    await pickFromBrowser(page, 'User 1');
    await page.getByRole('button', { name: '2D', exact: true }).click();
    await expect(page.locator('.view-3d')).toHaveCount(0);
    await expect(page.locator('.details-sidebar h2')).toHaveText('User 1');
  });

  test('the details panel is solid for people and topics, in 2D and 3D', async ({ page }) => {
    const panelStyle = () => page.locator('.details-sidebar').evaluate(el => {
      const { backgroundColor, backdropFilter } = getComputedStyle(el);
      return { backgroundColor, backdropFilter };
    });
    const solid = { backgroundColor: 'rgb(25, 28, 35)', backdropFilter: 'none' };
    await pickFromBrowser(page, 'User 0');
    expect(await panelStyle()).toEqual(solid);
    await page.getByRole('button', { name: /topic 0/ }).first().click();
    await expect(page.locator('.details-sidebar h2')).toHaveText('topic 0');
    expect(await panelStyle()).toEqual(solid);
    await page.getByRole('button', { name: '3D', exact: true }).click();
    await expect(page.locator('.view-3d')).toBeVisible();
    expect(await panelStyle()).toEqual(solid);
  });

  test('Home returns to the landing page', async ({ page }) => {
    await page.getByRole('button', { name: 'Home' }).click();
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Browse nodes' })).toHaveCount(0);
  });

  test('New chat opens the picker and keeps the graph until a file is chosen', async ({ page }) => {
    const [chooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.getByRole('button', { name: 'New chat' }).click(),
    ]);
    await expect(page.getByRole('button', { name: 'Browse nodes' })).toBeVisible();

    await pickFromBrowser(page, 'User 0');
    await chooser.setFiles({ name: 'other.txt', mimeType: 'text/plain', buffer: Buffer.from('x') });
    await expect(page.getByRole('button', { name: 'Browse nodes' })).toBeVisible();
    await expect(page.locator('.details-sidebar')).toHaveCount(0);
    await expect(page.getByRole('button', { name: /expanded message/ })).toHaveCount(0);
  });

  test('New chat rejecting a bad file explains why on the landing page', async ({ page }) => {
    await page.getByLabel('New chat export file').setInputFiles({ name: 'photo.png', mimeType: 'image/png', buffer: Buffer.from('x') });
    await expect(page.getByRole('alert')).toContainText("photo.png isn't a supported export");
  });

  test('landing and graph chunks stay out of each other\'s way', async ({ page }) => {
    const loaded = await page.evaluate(() => performance.getEntriesByType('resource').map(r => r.name));
    expect(loaded.some(n => n.includes('Graph2D'))).toBe(true);
    expect(loaded.some(n => n.includes('Graph3D'))).toBe(false);
  });
});

test('3D is unavailable at phone width', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await useFakePipeline(page, syntheticGraph(10));
  await page.goto('/');
  await uploadFixture(page);
  await expect(page.getByRole('button', { name: '3D', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Legend' })).toHaveAttribute('aria-expanded', 'false');
});

test('3D waits for the toggle before downloading three.js, and respects limits', async ({ page }) => {
  await useFakePipeline(page, syntheticGraph(2100));
  await page.goto('/');
  await uploadFixture(page);
  await page.getByRole('checkbox', { name: 'Show every message' }).check();
  await expect(page.getByRole('button', { name: '3D', exact: true })).toBeDisabled();
});

test.describe('landing page', () => {
  test('renders the interactive field and smooth scrolling', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('canvas.node-field')).toBeVisible();
    await expect(page.locator('html.lenis')).toHaveCount(1);
    await expect.poll(() => page.locator('.landing').evaluate(el => el.style.getPropertyValue('--flow'))).not.toBe('');
  });

  test('anchor link scrolls and shifts the accent color', async ({ page }) => {
    await page.goto('/');
    const before = await page.locator('.brand').evaluate(el => getComputedStyle(el).color);
    await page.getByRole('link', { name: 'How it works' }).click();
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(200);
    await expect.poll(() => page.locator('.brand').evaluate(el => getComputedStyle(el).color)).not.toBe(before);
  });

  test('phones use native scrolling and an unmasked canvas', async ({ browser }) => {
    const context = await browser.newContext({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 700 }, baseURL: 'http://localhost:4173' });
    const page = await context.newPage();
    await page.goto('/');
    const canvas = page.locator('canvas.node-field');
    await expect(canvas).toBeVisible();
    await expect(page.locator('html.lenis')).toHaveCount(0);
    expect(await canvas.evaluate(el => getComputedStyle(el).maskImage)).toBe('none');

    await context.close();
  });

  test('reduced motion turns off smooth scrolling', async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: 'reduce', baseURL: 'http://localhost:4173' });
    const page = await context.newPage();
    await page.goto('/');
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('html.lenis')).toHaveCount(0);
    await context.close();
  });

  test('an unsupported file shows an inline error', async ({ page }) => {
    await page.goto('/');
    await page.locator('input[type="file"]').setInputFiles({ name: 'photo.png', mimeType: 'image/png', buffer: Buffer.from('x') });
    await expect(page.getByRole('alert')).toContainText("photo.png isn't a supported export");
  });

  test('the drop zone is reachable by keyboard', async ({ page }) => {
    await page.goto('/');
    const target = page.getByRole('button', { name: /Drop a chat export/ });
    await target.focus();
    await expect(target).toBeFocused();
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.keyboard.press('Enter')]);
    expect(chooser.isMultiple()).toBe(false);
  });

  test('shows separate live bars for the model and embeddings', async ({ page }) => {
    await page.addInitScript(() => {
      window.Worker = class {
        postMessage({ id }) {
          const send = (delay, progress) => setTimeout(() => this.onmessage({ data: { id, progress } }), delay);
          send(0, { status: 'Loading embedding model…', model: { fraction: 0.5, loaded: 11e6, total: 22e6 } });
          send(600, { model: { fraction: 1 } });
          send(600, { status: 'Embedding messages…', embedding: { fraction: 0.25, done: 32, total: 128 } });
        }
      };
    });
    await page.goto('/');
    await page.locator('input[type="file"]').setInputFiles({ name: 'chat.txt', mimeType: 'text/plain', buffer: Buffer.from('x') });

    const model = page.getByRole('progressbar', { name: 'Embedding model' });
    const embedding = page.getByRole('progressbar', { name: 'Message embeddings' });
    await expect(model).toHaveAttribute('aria-valuenow', '50');
    await expect(page.getByText('11 / 22 MB')).toBeVisible();
    await expect(embedding).toHaveAttribute('aria-valuenow', '0');

    await expect(model).toHaveAttribute('aria-valuenow', '100');
    await expect(page.getByText('Ready', { exact: true })).toBeVisible();
    await expect(embedding).toHaveAttribute('aria-valuenow', '25');
    await expect(page.getByText('32 / 128')).toBeVisible();
  });

  test('has no glass effects', async ({ page }) => {
    await page.goto('/');
    const blurred = await page.locator('.landing, .landing *').evaluateAll(els => (
      els.filter(el => getComputedStyle(el).backdropFilter !== 'none').length
    ));
    expect(blurred).toBe(0);
  });

  test('has no horizontal overflow at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto('/');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});
