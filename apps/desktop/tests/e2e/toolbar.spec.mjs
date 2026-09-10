import { _electron as electron, expect, test } from '@playwright/test';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const root = path.resolve(appRoot, '../..');
// Playwright REQUIRES the first argument to be a destructuring pattern, and this
// test drives Electron rather than a page, so it takes no fixture from it. The
// empty pattern is the framework's contract, not an oversight.
// eslint-disable-next-line no-empty-pattern
test('CAD toolbar compacts to its scene and restores every tool on widening', async ({}, testInfo) => {
  test.setTimeout(120000);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'hardcore-toolbar-'));
  const output = testInfo.outputPath('screenshots');
  fs.mkdirSync(output, {
    recursive: true
  });
  const app = await electron.launch({
    args: [`${root}/apps/desktop/out/main/index.js`, `--user-data-dir=${profile}`],
    env: {
      ...process.env,
      NODE_ENV: 'test',
      HARDCORE_E2E_HIDDEN: '1',
      HARDCORE_FAKE_AGENT: `${root}/apps/desktop/tests/fake-agent/index.mjs`,
      CADGEN_DAEMON: '0'
    }
  });
  try {
    const page = await app.firstWindow();
    test.skip((await page.evaluate(() => window.hardcore.runtime.status())).state !== 'ready', 'CAD runtime required');
    const sourceRequests = [];
    page.on('request', request => { if (request.url().includes('/__cad/design-outline')) sourceRequests.push(request.url()); });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    let loading = false;
    await page.route('**/__cad/artifact?*', route => loading ? route.fulfill({
      json: {
        ok: true,
        state: 'compiling',
        runId: 'toolbar-loading-test',
        progress: {
          phase: 'mesh',
          label: 'Loading components',
          done: 12,
          total: 50,
          determinate: true
        }
      }
    }) : route.continue());
    await page.evaluate(() => window.hardcore.settings.set({
      theme: 'dark',
      reduceMotion: false,
      defaultGitMode: 'none',
      fetchBeforeCreate: false
    }));
    await page.evaluate(folder => window.hardcore.projects.addPath({
      path: folder
    }), root);
    await expect(page.locator('[data-explorer-ready=true]')).toBeVisible();
    await page.getByRole('button', {
      name: 'Toggle explorer',
      exact: true
    }).click();
    await page.getByRole('button', {
      name: 'New tab',
      exact: true
    }).click();
    await page.getByRole('menuitem', {
      name: 'File',
      exact: false
    }).click();
    await page.getByLabel('Filter files').fill('models/examples/imported/import-smoke.step');
    await page.getByRole('option', {
      name: 'models/examples/imported/import-smoke.step',
      exact: false
    }).first().click();
    await expect(page.getByLabel('Zoom level percent', {
      exact: true
    })).toBeVisible({
      timeout: 60000
    });
    const toolbar = page.locator('[data-cad-toolbar]');
    const resize = async width => app.evaluate(({
      BrowserWindow
    }, w) => BrowserWindow.getAllWindows()[0].setSize(w, 800), width);
    const fit = async () => {
      const metric = await toolbar.evaluate(el => {
        const scene = el.parentElement.getBoundingClientRect();
        return [...el.querySelectorAll('button,input')].filter(b => b.getClientRects().length).map(b => {
          const r = b.getBoundingClientRect();
          return {
            name: b.getAttribute('aria-label'),
            left: r.left,
            right: r.right,
            boundLeft: scene.left,
            boundRight: scene.right
          };
        });
      });
      assert(metric.every(x => x.left >= x.boundLeft - 1 && x.right <= x.boundRight + 1), JSON.stringify(metric));
    };
    await resize(1600);
    await expect(toolbar).toHaveAttribute('data-cad-toolbar', 'full');
    const fullLabels = await toolbar.getByRole('button').evaluateAll(els => els.map(el => el.getAttribute('aria-label')));
    const view = toolbar.getByRole('group', { name: 'View', exact: true });
    const inspect = toolbar.getByRole('group', { name: 'Inspect', exact: true });
    const markup = toolbar.getByRole('group', { name: 'Markup and capture', exact: true });
    const grouping = async () => {
      for (const name of ['View controls', 'Display', 'Reset view']) await expect(view.getByRole('button', { name, exact: true })).toBeVisible();
      for (const name of ['Select', 'Selection filter: All', 'Measure']) await expect(inspect.getByRole('button', { name, exact: true })).toBeVisible();
      for (const name of ['Draw', 'Capture']) await expect(markup.getByRole('button', { name, exact: true })).toBeVisible();
      await expect(toolbar.getByRole('button', { name: 'More tools' })).toHaveCount(0);
      await fit();
    };
    await grouping();
    await page.screenshot({ path: `${output}/wide.png` });
    await resize(960);
    await expect(toolbar).toHaveAttribute('data-cad-toolbar', 'compact');
    await grouping();
    await page.screenshot({ path: `${output}/narrow.png` });

    await view.getByRole('button', { name: 'View controls' }).click();
    for (const name of ['Pan', 'Orbit']) await expect(page.getByRole('menuitem', { name, exact: true })).toBeEnabled();
    await expect(page.getByRole('menuitem', { name: 'Copy screenshot' })).toHaveCount(0);
    await page.getByRole('menuitem', { name: 'Pan', exact: true }).click();
    await view.getByRole('button', { name: 'View controls' }).click();
    await expect(page.getByRole('menuitem', { name: /Pan/ }).getByLabel('Active')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(view.getByRole('button', { name: 'View controls' })).toBeFocused();

    await markup.getByRole('button', { name: 'Capture', exact: true }).click();
    for (const name of ['Copy screenshot', 'Ask about this view']) await expect(page.getByRole('menuitem', { name, exact: true })).toBeEnabled();
    await expect(page.getByRole('menuitem', { name: 'Orbit' })).toHaveCount(0);
    await expect(page.getByRole('menu')).toHaveCSS('opacity', '1');
    await page.screenshot({ path: `${output}/narrow-menu.png` });
    const menuBounds = await page.getByRole('menu').boundingBox();
    const windowWidth = await page.evaluate(() => innerWidth);
    assert(menuBounds.x >= 0 && menuBounds.x + menuBounds.width <= windowWidth);
    await page.keyboard.press('Escape');
    await expect(markup.getByRole('button', { name: 'Capture', exact: true })).toBeFocused();

    await markup.getByRole('button', { name: 'Draw', exact: true }).click();
    await expect(toolbar.getByRole('button', { name: 'Drawing tool: Freehand', exact: true })).toBeVisible();
    await fit();
    await markup.getByRole('button', { name: 'Capture', exact: true }).click();
    await resize(1600);
    await expect(toolbar).toHaveAttribute('data-cad-toolbar', 'full');
    await expect(page.getByRole('menu')).toHaveCount(0);
    await expect(markup.getByRole('button', { name: 'Draw', exact: true })).toHaveAttribute('aria-pressed', 'true');
    assert.deepEqual((await toolbar.getByRole('button').evaluateAll(els => els.map(el => el.getAttribute('aria-label')))).slice(0, fullLabels.length), fullLabels);
    await inspect.getByRole('button', { name: 'Select', exact: true }).click();
    await resize(960);
    await expect(toolbar).toHaveAttribute('data-cad-toolbar', 'compact');
    await grouping();
    await view.getByRole('button', { name: 'View controls' }).click();
    await page.getByRole('menuitem', { name: 'Orbit', exact: true }).click();
    await expect(toolbar.getByRole('button', { name: 'Exit orbit', exact: true })).toBeVisible();
    await fit();
    await toolbar.getByRole('button', { name: 'Exit orbit', exact: true }).click();
    await expect(toolbar).toHaveAttribute('data-cad-toolbar', 'compact');
    await page.evaluate(() => window.hardcore.settings.set({ theme: 'light', reduceMotion: true }));
    await markup.getByRole('button', { name: 'Capture', exact: true }).click();
    await page.screenshot({ path: `${output}/narrow-menu-light.png` });
    await page.keyboard.press('Escape');
    loading = true;
    await page.reload();
    await expect(page.getByText('12/50', { exact: true })).toBeVisible();
    await fit();
    for (const name of ['Select', 'Measure', 'Draw', 'Display']) await expect(toolbar.getByRole('button', { name, exact: true })).toBeDisabled();
    await view.getByRole('button', { name: 'View controls' }).click();
    for (const name of ['Pan', 'Orbit']) await expect(page.getByRole('menuitem', { name, exact: true })).toBeDisabled();
    await page.keyboard.press('Escape');
    await markup.getByRole('button', { name: 'Capture', exact: true }).click();
    for (const name of ['Copy screenshot', 'Ask about this view']) await expect(page.getByRole('menuitem', { name, exact: true })).toBeDisabled();
    assert.deepEqual(errors, []);
    assert.deepEqual(sourceRequests, []);
    await expect(page.getByRole('tab', { name: 'Source features' })).toHaveCount(0);
    console.info('PASS: semantic groups at both widths; View and Capture menus; Draw; Pan/Orbit; focus; scene bounds; loading; no renderer errors');
  } finally {
    await app.close();
    fs.rmSync(profile, {
      recursive: true,
      force: true
    });
  }
});
