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
test('Model tree preserves part controls and adds precise viewport references to the prompt', async ({}, testInfo) => {
  test.setTimeout(120000);
  const profile = cadTestProfile('surfaces');
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
    await expect(page.locator('[data-file-sheet-header]')).toBeVisible({
      timeout: 60000
    });
    await expect(page.getByRole('tab',{name:'Model',exact:true})).toBeVisible();
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
    // Expanded parts expose exact topology. All mode may select inferred
    // feature groups, so request Faces explicitly for this precise-ref check.
    await tree.getByRole('button',{name:'Expand import-smoke.step',exact:true}).click();
    await expect(tree.getByRole('button',{name:/^Select Base (extrude|revolve)$/}).first()).toBeVisible({timeout:30000});
    await page.getByRole('button',{name:'Selection filter: All',exact:true}).click();
    await page.getByRole('menuitemradio',{name:'Faces Faces only',exact:true}).click();
    const selectTool = page.getByRole('button', {name:'Select', exact:true});
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
    const runtimeLog = path.join(profile, 'cad-runtime.log');
    if (fs.existsSync(runtimeLog)) fs.copyFileSync(runtimeLog, testInfo.outputPath('cad-runtime.log'));
    await app.close();
    fs.rmSync(profile,{recursive:true,force:true});
  }
});
