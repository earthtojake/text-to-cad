import { _electron as electron, expect, test } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { cadRegistryEnvironment, cadRuntimeReady, cadTestProfile } from './cad-runtime.ts';
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const root = path.resolve(appRoot, '../..');
// Playwright REQUIRES the first argument to be a destructuring pattern, and this
// test drives Electron rather than a page, so it takes no fixture from it. The
// empty pattern is the framework's contract, not an oversight.
// eslint-disable-next-line no-empty-pattern
test('Model tree preserves part controls and adds precise viewport references to the prompt', async ({}, testInfo) => {
  test.setTimeout(120000);
  const profile = cadTestProfile('surfaces');
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
  try {
    const page = await app.firstWindow();
    test.skip(!cadRuntimeReady(await page.evaluate(() => window.hardcore.runtime.status())), 'CAD runtime required');
    const sourceRequests = [];
    page.on('request', request => { if (/\/__cad\/(design-outline|reconstruction)/.test(request.url())) sourceRequests.push(request.url()); });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
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
    await expect(page.getByRole('tab',{name:'Model',exact:true})).toHaveCount(0);
    await expect(page.locator('[data-file-sheet-tab-panel=tree]')).toBeVisible();
    await expect(page.getByRole('tab',{name:'Surfaces',exact:true})).toHaveCount(0);
    await expect(page.getByRole('tab',{name:'Geometry',exact:true})).toHaveCount(0);
    await expect(page.getByRole('tab',{name:'Features',exact:true})).toHaveCount(0);
    const tree=page.getByRole('list',{name:'Model',exact:true});
    const part=tree.getByRole('button',{name:/^Select /}).first();
    await expect(part).toBeVisible({timeout:30000});
    await part.click();
    await page.getByText('Dimension previews',{exact:true}).click();
    await expect(page.getByRole('button',{name:'Show X extent',exact:true})).toBeVisible();
    await tree.getByRole('button',{name:/^Hide /}).first().click();
    await expect(tree.getByRole('button',{name:/^Reveal /}).first()).toBeVisible();
    await page.getByRole('button',{name:'Show all',exact:true}).click();
    await expect(tree.getByRole('button',{name:/^Hide /}).first()).toBeVisible();
    // Explicit selection requests exact topology; the initial display remains lightweight.
    const selectTool = page.getByRole('button', {name:'Select', exact:true});
    await selectTool.click();
    await expect(selectTool).toBeEnabled({timeout:30000});
    // Pick the model itself; no exhaustive topology list is needed to inspect faces or edges.
    const canvas=page.locator('[data-cad-surface] canvas').first();
    const box=await canvas.boundingBox();
    await page.screenshot({path:`${output}/before-pick.png`,animations:'disabled'});
    await canvas.click({position:{x:box.width*0.5,y:box.height*0.5}});
    await page.screenshot({path:`${output}/after-pick.png`,animations:'disabled'});
    await expect(page.getByRole('button',{name:'Add to prompt',exact:true})).toBeVisible();
    const reference=page.locator('[data-file-sheet-tab-panel=tree]').getByText(/^o[0-9.]+\.[fe][0-9]+$/);
    await expect(reference).toBeVisible();
    const selector=await reference.innerText();
    await page.getByRole('button',{name:'Add to prompt',exact:true}).click();
    const chip=page.locator('[data-composer] [data-reference-chip]');
    await expect(chip).toHaveCount(1);
    await expect(chip).toHaveAttribute('data-file','tests/fixtures/cad/import-smoke.step');
    await expect(chip).toHaveAttribute('data-selector',selector);
    await expect(page.locator('[data-composer]')).not.toContainText('.py');
    await expect(page.getByRole('button',{name:/Play (build|assembly)/})).toHaveCount(0);
    await page.screenshot({path:`${output}/selection-summary.png`});
    // Clearing inspection must also clear the viewport selection, while preserving the draft reference.
    await page.getByRole('button',{name:'Clear selection',exact:true}).click();
    await expect(page.getByRole('region',{name:'Modeling details',exact:true})).toHaveCount(0);
    await expect(page.getByRole('button',{name:'Add to prompt',exact:true})).toHaveCount(0);
    await expect(chip).toHaveCount(1);
    assert.deepEqual(sourceRequests,[]);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:`${output}/surfaces.png`});
  } finally {
    await app.close();
    fs.rmSync(profile,{recursive:true,force:true});
  }
});
