import { _electron as electron, expect, test } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { cadRegistryEnvironment, cadRuntimeReady, cadTestProfile } from './cad-runtime.ts';
import { selectFixtureSession } from './session-fixture.ts';
import { widenExplorer } from './viewer-layout.ts';
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const root = path.resolve(appRoot, '../..');
// Playwright REQUIRES the first argument to be a destructuring pattern, and this
// test drives Electron rather than a page, so it takes no fixture from it. The
// empty pattern is the framework's contract, not an oversight.
// eslint-disable-next-line no-empty-pattern
test('the Features tree presents a lone part as its features, and precise viewport references reach the prompt', async ({}, testInfo) => {
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
    // The wide layout: the tree stays up across a pick and the Settings panel is a column.
    await widenExplorer(page);
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
    // Picked in the tree, the STEP opens with the tree still up, and its own Settings one press away.
    const partPanel = page.locator('header [data-file-panel=cad-file]');
    await expect(partPanel).toHaveAttribute('aria-label','Settings', { timeout: 60000 });
    await expect(page.getByTestId('tree-toggle')).toHaveAttribute('aria-pressed','true');
    await partPanel.click();
    await expect(page.locator('[data-file-sheet=Settings]')).toBeVisible();
    // The tree is the panel's Features section — with no joints and no issues, its only one —
    // and there are no tabs at all: the Model, Surfaces and Geometry tabs are gone with the rest.
    await expect(page.getByRole('region',{name:'Features',exact:true})).toBeVisible();
    await expect(page.locator('[data-file-panel-section=features]')).toBeVisible();
    await expect(page.locator('[data-file-sheet=Settings] [data-file-panel-section]')).toHaveCount(1);
    await expect(page.locator('[data-file-sheet]').getByRole('tab')).toHaveCount(0);
    for (const retired of ['Model','Surfaces','Geometry']) await expect(page.getByRole('region',{name:retired,exact:true})).toHaveCount(0);
    const tree=page.getByRole('list',{name:'Model',exact:true});
    // A lone part is presented as its features directly: the part itself adds no choice.
    const feature=tree.getByRole('button',{name:/^Select Base (extrude|revolve)$/}).first();
    await expect(feature).toBeVisible({timeout:30000});
    await expect(tree.getByRole('button',{name:'Select import-smoke.step',exact:true})).toHaveCount(0);
    // A feature row carries the viewport's menu over its faces, and its Select is the row's click.
    await feature.click({button:'right'});
    await expect(page.getByRole('menu').getByRole('menuitem')).toHaveText(['Add to prompt','Copy Reference','Select','Zoom to fit','Zoom to selection']);
    await page.getByRole('menuitem',{name:'Select',exact:true}).click();
    await expect(page.getByRole('menu')).toHaveCount(0);
    await expect(feature).toHaveAttribute('aria-pressed','true');
    await page.keyboard.press('Escape');
    await expect(feature).toHaveAttribute('aria-pressed','false');
    // Precise refs: the Select tool's second press narrows its filter to faces.
    const selectTool = page.getByRole('group',{name:'Interaction tools',exact:true}).getByRole('button', {name:'Select', exact:true});
    await expect(selectTool).toBeEnabled({timeout:30000});
    await expect(selectTool).toHaveAttribute('aria-pressed','true');
    await selectTool.click();
    await page.getByRole('menuitemradio',{name:/^Faces/}).click();
    await expect(page.getByRole('menu')).toHaveCount(0);
    // Pick the model itself; no exhaustive topology list is needed to inspect faces or edges.
    const canvas=page.locator('[data-cad-surface] canvas').first();
    const box=await canvas.boundingBox();
    await page.screenshot({path:`${output}/before-pick.png`,animations:'disabled'});
    await canvas.click({position:{x:box.width*0.5,y:box.height*0.5}});
    await page.screenshot({path:`${output}/after-pick.png`,animations:'disabled'});
    // A usable selection earns the viewer's one bottom action, Copy Reference (with its shortcut);
    // the prompt is reached through the pick's own menu.
    const copyAction=page.getByRole('button',{name:/^Copy Reference\b/});
    await expect(copyAction).toBeVisible();
    await expect(page.getByRole('button',{name:'Add to prompt',exact:true})).toHaveCount(0);
    // The pick's Reference, pinned at the Settings panel's foot under its sections.
    const reference=page.locator('[data-file-sheet=Settings]').getByRole('region',{name:'Reference details',exact:true}).getByText(/^o[0-9.]+\.[fe][0-9]+$/);
    await expect(reference).toBeVisible();
    const selector=await reference.innerText();
    await canvas.click({button:'right',position:{x:box.width*0.5,y:box.height*0.5}});
    await page.getByRole('menuitem',{name:'Add to prompt',exact:true}).click();
    await expect(page.getByRole('menu')).toHaveCount(0);
    const chip=page.locator('[data-composer] [data-reference-chip]');
    await expect(chip).toHaveCount(1);
    await expect(chip).toHaveAttribute('data-file','tests/fixtures/cad/import-smoke.step');
    await expect(chip).toHaveAttribute('data-selector',selector);
    await expect(page.locator('[data-composer]')).not.toContainText('.py');
    await expect(page.getByRole('button',{name:/Play (build|assembly)/})).toHaveCount(0);
    await page.screenshot({path:`${output}/selection-summary.png`});
    // Clearing inspection must also clear the viewport selection, while preserving the draft reference.
    await page.getByRole('button',{name:'Clear selection',exact:true}).click();
    await expect(page.getByRole('region',{name:'Reference details',exact:true})).toHaveCount(0);
    await expect(copyAction).toHaveCount(0);
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
