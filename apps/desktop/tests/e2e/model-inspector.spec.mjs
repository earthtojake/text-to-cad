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
test('Model tree groups collapsed faces and adds measured STEP references to the prompt', async ({}, testInfo) => {
  test.setTimeout(120000);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'hardcore-surfaces-'));
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
    await expect(page.getByRole('tab',{name:'Model',exact:true})).toBeVisible();
    await expect(page.getByRole('tab',{name:'Surfaces',exact:true})).toHaveCount(0);
    const tree=page.getByRole('tree',{name:'Model',exact:true});
    await tree.getByRole('treeitem').first().click();
    await expect(tree.getByRole('button',{name:/^Expand Faces/})).toBeVisible({timeout:60000});
    await expect(tree.locator('[data-step-tree-node-type="topology-face"]')).toHaveCount(0);
    await page.getByRole('button',{name:'Face list: Individual faces',exact:true}).click();
    await page.getByRole('menuitemradio',{name:'By surface type',exact:true}).click();
    await tree.getByRole('button',{name:/^Expand Faces/}).click();
    const planar=tree.getByText(/^Planar \(\d+\)$/);
    await expect(planar).toBeVisible();
    await planar.click();
    await expect(page.getByText('Face area',{exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Show X extent',exact:true}).click();
    await expect(page.getByRole('button',{name:'Show X extent',exact:true})).toHaveAttribute('aria-pressed','true');
    await page.getByRole('button',{name:'Add to prompt',exact:true}).click();
    const chip=page.locator('[data-composer] [data-reference-chip]');
    await expect(chip).toHaveCount(1);
    await expect(chip).toHaveAttribute('data-file','models/examples/imported/import-smoke.step');
    await expect(chip).toHaveAttribute('data-selector',/f[0-9]/);
    await expect(page.locator('[data-composer]')).not.toContainText('.py');
    await expect(page.getByRole('tab',{name:'Source features'})).toHaveCount(0);
    assert.deepEqual(sourceRequests,[]);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:`${output}/surfaces.png`});
  } finally {
    await app.close();
    fs.rmSync(profile,{recursive:true,force:true});
  }
});
