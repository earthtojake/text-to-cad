import { _electron as electron, expect, test } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const fixture = 'models/examples/imported/import-smoke.step';

for (const enabled of [false, true]) {
  // Electron owns the window; this test intentionally takes no browser fixture.
  // eslint-disable-next-line no-empty-pattern
  test(`STEP reconstruction is ${enabled ? 'available with verified playback and GIF export' : 'entirely inactive by default'}`, async ({}, testInfo) => {
    test.setTimeout(120000);
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'hardcore-reconstruction-'));
    const app = await electron.launch({
      args: [path.join(root, 'apps/desktop/out/main/index.js'), `--user-data-dir=${profile}`],
      env: { ...process.env, NODE_ENV: 'test', HARDCORE_E2E_HIDDEN: '1', CADGEN_DAEMON: '0',
        CADGEN_RECONSTRUCTION_EXPERIMENT: enabled ? '1' : '0' },
    });
    try {
      const page = await app.firstWindow();
      test.skip((await page.evaluate(() => window.hardcore.runtime.status())).state !== 'ready', 'CAD runtime required');
      const workers = [], requests = [], errors = [];
      page.on('worker', worker => workers.push(worker.url()));
      page.on('request', request => requests.push(request.url()));
      page.on('pageerror', error => errors.push(error.message));
      await page.evaluate(() => window.hardcore.settings.set({ theme: 'dark', defaultGitMode: 'none', fetchBeforeCreate: false }));
      await page.evaluate(folder => window.hardcore.projects.addPath({ path: folder }), root);
      await expect(page.locator('[data-explorer-ready=true]')).toBeVisible();
      await page.getByRole('button', { name: 'Toggle explorer', exact: true }).click();
      await page.getByRole('button', { name: 'New tab', exact: true }).click();
      await page.getByRole('menuitem', { name: 'File', exact: false }).click();
      await page.getByLabel('Filter files').fill(fixture);
      await page.getByRole('option', { name: fixture, exact: false }).first().click();
      await expect(page.getByLabel('Zoom level percent', { exact: true })).toBeVisible({ timeout: 60000 });
      if (!enabled) {
        await expect(page.getByRole('tree', { name: 'Model', exact: true })).toBeVisible();
        await expect(page.getByRole('tab', { name: 'features', exact: true })).toHaveCount(0);
        expect(workers.filter(url => url.includes('modelingTree.worker'))).toEqual([]);
        expect(requests.filter(url => url.includes('/__cad/reconstruction'))).toEqual([]);
      } else {
        await page.getByRole('tab', { name: 'features', exact: true }).click();
        await page.getByRole('button', { name: 'Play build sequence', exact: true }).click({ timeout: 60000 });
        await expect(page.getByText('Final geometry matches', { exact: true })).toBeVisible();
        await page.getByRole('button', { name: 'Replay', exact: true }).click();
        await expect(page.getByRole('slider', { name: 'Build step' })).toHaveValue('0');
        await page.getByRole('button', { name: 'Pause', exact: true }).click();
        await page.getByRole('button', { name: 'Original STEP', exact: true }).click();
        await expect(page.getByLabel('Original STEP solid', { exact: true })).toBeVisible();
        const output = testInfo.outputPath('build.gif');
        // Exercise Electron's real download while choosing a path in place of
        // its native save dialog (which cannot be clicked in a hidden test).
        await app.evaluate(({ BrowserWindow }, output) => {
          globalThis.reconstructionDownload = null;
          BrowserWindow.getAllWindows()[0].webContents.session.once('will-download', (_event, item) => {
            item.setSavePath(output);
            item.once('done', (_event, state) => { globalThis.reconstructionDownload = state; });
          });
        }, output);
        await page.getByRole('button', { name: 'Export', exact: true }).click();
        await page.getByRole('menuitem', { name: 'Animated GIF', exact: true }).click();
        await expect.poll(() => app.evaluate(() => globalThis.reconstructionDownload), { timeout: 15000 }).toBe('completed');
        const bytes = fs.readFileSync(output);
        expect(bytes.subarray(0, 6).toString()).toBe('GIF89a');
        expect(bytes.readUInt16LE(6)).toBe(800);
        expect(bytes.readUInt16LE(8)).toBe(514);
        expect(bytes.length).toBeGreaterThan(1000);
        await page.getByRole('button', { name: 'Close', exact: true }).click();
        await page.getByRole('tab', { name: 'geometry', exact: true }).click();
        await expect(page.getByRole('tree', { name: 'Model', exact: true })).toBeVisible();
      }
      expect(requests.filter(url => url.includes('/__cad/design-outline'))).toEqual([]);
      expect(errors).toEqual([]);
    } finally {
      await app.close();
      fs.rmSync(profile, { recursive: true, force: true });
    }
  });
}
