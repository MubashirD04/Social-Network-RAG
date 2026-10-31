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
