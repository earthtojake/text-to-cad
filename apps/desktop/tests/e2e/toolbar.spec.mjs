import { _electron as electron, expect, test } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { cadRegistryEnvironment, cadRuntimeReady, cadTestProfile } from './cad-runtime.ts';
import { selectFixtureSession } from './session-fixture.ts';
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const root = path.resolve(appRoot, '../..');
// Playwright REQUIRES the first argument to be a destructuring pattern, and this
// test drives Electron rather than a page, so it takes no fixture from it. The
// empty pattern is the framework's contract, not an oversight.
// eslint-disable-next-line no-empty-pattern
test('CAD toolbar compacts to its scene and restores every tool on widening', async ({}, testInfo) => {
  test.setTimeout(120000);
  const profile = cadTestProfile('toolbar');
  // CAD checks own a tiny project; catalog resolution must not scan the repo's
  // sample models, local bundles or unrelated workspaces.
  const project = path.join(profile, 'project');
  const fixture = 'tests/fixtures/cad/import-smoke.step';
  fs.mkdirSync(path.dirname(path.join(project, fixture)), { recursive: true });
  fs.copyFileSync(path.join(root, fixture), path.join(project, fixture));
  const output = testInfo.outputPath('screenshots');
  fs.mkdirSync(output, {
    recursive: true
  });
  const app = await electron.launch({
    args: [`${root}/apps/desktop/out/main/index.js`, `--user-data-dir=${profile}`],
    env: {
      ...process.env,
      ...cadRegistryEnvironment(profile),
      NODE_ENV: 'test',
      HARDCORE_E2E_HIDDEN: '1',
      HARDCORE_FAKE_AGENT: `${root}/apps/desktop/tests/fake-agent/index.mjs`,
      CADGEN_DAEMON: '0',
      CADGEN_CACHE_DIR: path.join(profile, 'cad-cache'),
      CADGEN_DAEMON_STATE_DIR: path.join(profile, 'cad-daemon')
    }
  });
  let page;
  try {
    page = await app.firstWindow();
    test.skip(!cadRuntimeReady(await page.evaluate(() => window.hardcore.runtime.status())), 'CAD runtime required');
    const sourceRequests = [];
    page.on('request', request => { if (request.url().includes('/__cad/design-outline')) sourceRequests.push(request.url()); });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    let loading = false;
    await page.route(/\/__cad\/catalog(?:\?|$)/, async route => {
      if (!loading) return route.continue();
      const response = await route.fetch();
      const catalog = await response.json();
      // A build with a saved view keeps that view interactive. Model the cold
      // build contract here: no complete geometry exists to display yet.
      await route.fulfill({ response, json: { ...catalog, entries: catalog.entries.map(entry =>
        entry.file.endsWith('/import-smoke.step')
          ? { ...entry, url: '', hash: '', bytes: 0 }
          : entry) } });
    });
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
    await selectFixtureSession(page, project);
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
    await page.getByLabel('Filter files').fill('tests/fixtures/cad/import-smoke.step');
    await page.getByRole('option', {
      name: 'tests/fixtures/cad/import-smoke.step',
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
    const view = toolbar.getByRole('group', { name: 'View and actions', exact: true });
    const tools = toolbar.getByRole('group', { name: 'Interaction tools', exact: true });
    const zoom = page.getByRole('group', { name: 'Zoom controls', exact: true });
    const grouping = async () => {
      for (const name of ['View controls', 'Display', 'Selection filter: All', 'Capture']) await expect(view.getByRole('button', { name, exact: true })).toBeVisible();
      for (const name of ['Select', 'Measure', 'Draw']) await expect(tools.getByRole('button', { name, exact: true })).toBeVisible();
      for (const name of ['Zoom out', 'Zoom in', 'Reset view']) await expect(zoom.getByRole('button', { name, exact: true })).toBeVisible();
      await expect(zoom.locator('input')).toHaveCount(0);
      await expect(toolbar.getByRole('group', { name: 'Zoom controls', exact: true })).toHaveCount(0);
      await expect(toolbar.getByRole('button', { name: 'More tools' })).toHaveCount(0);
      const cameraBounds = await zoom.boundingBox();
      const axisBounds = await page.getByRole('img', { name: 'Perspective selector', exact: true }).boundingBox();
      assert(cameraBounds.y + cameraBounds.height <= axisBounds.y + 1, 'zoom controls sit above the orientation axes');
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

    await view.getByRole('button', { name: 'Capture', exact: true }).click();
    for (const name of ['Copy screenshot', 'Ask about this view']) await expect(page.getByRole('menuitem', { name, exact: true })).toBeEnabled();
    await expect(page.getByRole('menuitem', { name: 'Orbit' })).toHaveCount(0);
    await expect(page.getByRole('menu')).toHaveCSS('opacity', '1');
    await page.screenshot({ path: `${output}/narrow-menu.png` });
    const menuBounds = await page.getByRole('menu').boundingBox();
    const windowWidth = await page.evaluate(() => innerWidth);
    assert(menuBounds.x >= 0 && menuBounds.x + menuBounds.width <= windowWidth);
    await page.keyboard.press('Escape');
    await expect(view.getByRole('button', { name: 'Capture', exact: true })).toBeFocused();

    await tools.getByRole('button', { name: 'Draw', exact: true }).click();
    await expect(toolbar.getByRole('button', { name: 'Drawing tool: Freehand', exact: true })).toBeVisible();
    await fit();
    await view.getByRole('button', { name: 'Capture', exact: true }).click();
    await resize(1600);
    await expect(toolbar).toHaveAttribute('data-cad-toolbar', 'full');
    await expect(page.getByRole('menu')).toHaveCount(0);
    await expect(tools.getByRole('button', { name: 'Draw', exact: true })).toHaveAttribute('aria-pressed', 'true');
    assert.deepEqual((await toolbar.getByRole('button').evaluateAll(els => els.map(el => el.getAttribute('aria-label')))).slice(0, fullLabels.length), fullLabels);
    await tools.getByRole('button', { name: 'Select', exact: true }).click();
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
    await view.getByRole('button', { name: 'Capture', exact: true }).click();
    await page.screenshot({ path: `${output}/narrow-menu-light.png` });
    await page.keyboard.press('Escape');
    loading = true;
    await page.reload();
    // Reload opens the new-session screen; restore this session's explorer
    // before exercising its cold-compilation toolbar state.
    await selectFixtureSession(page, project);
    await expect(page.getByText('12/50', { exact: true })).toBeVisible();
    await fit();
    for (const name of ['Select', 'Measure', 'Draw', 'Display']) await expect(toolbar.getByRole('button', { name, exact: true })).toBeDisabled();
    await view.getByRole('button', { name: 'View controls' }).click();
    for (const name of ['Pan', 'Orbit']) await expect(page.getByRole('menuitem', { name, exact: true })).toBeDisabled();
    await page.keyboard.press('Escape');
    await view.getByRole('button', { name: 'Capture', exact: true }).click();
    for (const name of ['Copy screenshot', 'Ask about this view']) await expect(page.getByRole('menuitem', { name, exact: true })).toBeDisabled();
    assert.deepEqual(errors, []);
    assert.deepEqual(sourceRequests, []);
    await expect(page.getByRole('tab', { name: 'Source features' })).toHaveCount(0);
    console.info('PASS: semantic groups at both widths; View and Capture menus; Draw; Pan/Orbit; focus; scene bounds; loading; no renderer errors');
  } finally {
    await page?.unrouteAll({ behavior: 'wait' });
    const runtimeLog = path.join(profile, 'cad-runtime.log');
    if (fs.existsSync(runtimeLog)) fs.copyFileSync(runtimeLog, testInfo.outputPath('cad-runtime.log'));
    await app.close();
    fs.rmSync(profile, {
      recursive: true,
      force: true
    });
  }
});
