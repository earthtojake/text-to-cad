import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test';
import type { HardcoreApi } from '../../src/shared/ipc';
import type { IntegrationCommand, IntegrationReply } from '../../src/shared/ipc/integrations';
// Keep React/DOM declarations out of the plain Node Electron test project.
type CadLiveState = { active: boolean; loading: boolean; revision: string;
  resource: { kind: string; path?: string; revision?: string }; selection: unknown[];
  camera: { position: [number, number, number]; target: [number, number, number]; up: [number, number, number];
    projection?: 'orthographic' | 'perspective'; focalLength?: number } | null;
  display: { mode: string; camera?: { enabled?: boolean; projection?: string; focalLength?: number } }; renderMode: string };
import { cadRegistryEnvironment, cadRuntimeReady, cadTestProfile } from './cad-runtime';
import { selectFixtureSession } from './session-fixture';

declare const window: { hardcore: HardcoreApi; __cadCamera?: () => { position: number[]; target: number[]; projection: string } | null };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
let app: ElectronApplication;
let project: string;
let profile: string;
let sequence = 0;
test.afterAll(async () => { await app?.close(); if (project) fs.rmSync(project, { recursive: true, force: true }); if (profile) fs.rmSync(profile, { recursive: true, force: true }); });

test('live CAD commands observe and control the mounted tiny STEP viewport without prompt effects', async () => {
  test.setTimeout(150_000);
  project = fs.mkdtempSync(path.join(os.tmpdir(), 'hc-cad-live-project-'));
  const bytes = fs.readFileSync(path.join(appRoot, '../../tests/fixtures/cad/import-smoke.step'));
  fs.writeFileSync(path.join(project, 'part.step'), bytes);
  const revision = createHash('sha256').update(bytes).digest('hex');
  profile = cadTestProfile('cad-live');
  app = await electron.launch({ args: [path.join(appRoot, 'out/main/index.js'), `--user-data-dir=${profile}`],
    env: { ...process.env, ...cadRegistryEnvironment(profile), NODE_ENV: 'test', HARDCORE_FAKE_AGENT: path.join(appRoot, 'tests/fake-agent/index.mjs'),
      CADGEN_DAEMON: '0', CADGEN_CACHE_DIR: path.join(profile, 'cad-cache'), CADGEN_DAEMON_STATE_DIR: path.join(profile, 'cad-daemon') } });
  const page = await app.firstWindow(); await page.waitForLoadState('domcontentloaded');
  const runtime = await page.evaluate(() => window.hardcore.runtime.status());
  test.skip(!cadRuntimeReady(runtime), 'CAD runtime required');
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.evaluate(() => window.hardcore.settings.set({ reduceMotion: true, defaultGitMode: 'none', fetchBeforeCreate: false }));
  const session = await selectFixtureSession(page, project);
  await expect(page.locator('[data-explorer-ready=true]')).toBeVisible();
  await page.getByRole('button', { name: 'Toggle explorer', exact: true }).click();
  // Intercept only this test window's replies. Production renderer dispatch and
  // viewport bindings still run, while the global app/MCP reply handler is intact.
  await app.evaluate(({ BrowserWindow }) => {
    const view = BrowserWindow.getAllWindows()[0]!.webContents;
    const replies = new Map<string, unknown>();
    (globalThis as unknown as { cadLiveReplies: Map<string, unknown> }).cadLiveReplies = replies;
    view.ipc.handle('hardcore:integrations.reply', (_event, reply: { requestId: string }) => { replies.set(reply.requestId, reply); });
  });
  async function reply(kind: IntegrationCommand['kind'], tabId?: string, params?: Record<string, unknown>): Promise<IntegrationReply> {
    const requestId = `live-${++sequence}`;
    await app.evaluate(({ BrowserWindow }, command) => BrowserWindow.getAllWindows()[0]!.webContents.send('hardcore!integrations.command', command),
      { requestId, kind, sessionId: session.id, projectId: session.projectId, root: null, ...(tabId ? { tabId } : {}), ...(params ? { params } : {}), ...(kind === 'open-file' ? { path: 'part.step' } : {}) });
    let result: IntegrationReply | null = null;
    await expect.poll(async () => {
      result = await app.evaluate((_electron, id) => (globalThis as unknown as { cadLiveReplies: Map<string, IntegrationReply> }).cadLiveReplies.get(id) ?? null, requestId);
      return result !== null;
    }).toBe(true);
    return result!;
  }
  async function command(kind: IntegrationCommand['kind'], tabId?: string, params?: Record<string, unknown>) {
    const result = await reply(kind, tabId, params); expect(result.ok, result.error).toBe(true); return result.result;
  }
  const opened = await command('open-file') as { tabId: string };
  const tabId = opened.tabId;
  await expect(page.locator('[data-cad-surface] canvas').first()).toBeVisible({ timeout: 90_000 });
  // Opened by a command rather than picked in the tree, the STEP opens in Select with its
  // Features in the tool stack under the toolbar and the file tree closed: the nav row's only
  // panel toggle is the file tree's, and Display is a tool whose panel is not up yet.
  const stack = page.locator('[data-cad-tool-stack]');
  await expect(stack.getByRole('region', { name: 'Features', exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.locator('header [data-file-panel]')).toHaveCount(1);
  await expect(page.locator('header [data-file-panel=tree]')).toHaveCount(1);
  await expect(stack.locator('[data-tool-panel][aria-label="Display settings"]')).toHaveCount(0);
  await expect(page.getByTestId('tree-toggle')).toHaveAttribute('aria-pressed', 'false');
  let state!: CadLiveState;
  await expect.poll(async () => {
    const result = await reply('viewer-state', tabId); if (!result.ok) return false;
    state = result.result as CadLiveState; return state.active && !state.loading && state.camera !== null;
  }, { timeout: 90_000 }).toBe(true);
  expect(state.resource).toMatchObject({ kind: 'workspace-file', path: 'part.step', revision });
  expect(state.revision).toBe(revision);
  expect(state.display).toEqual({ mode: 'solid' });
  const initialCamera = state.camera!;
  // Select's default mode is All: a press on a lone part picks the face under the pointer, and
  // the pick's Reference joins the stack under Features.
  const selectTool = page.getByRole('group', { name: 'Interaction tools', exact: true }).getByRole('button', { name: 'Select', exact: true });
  await expect(selectTool).toHaveAttribute('aria-pressed', 'true');
  await expect(selectTool.locator('[data-select-mode]')).toHaveAttribute('data-select-mode', 'all');
  const canvas = page.locator('[data-cad-surface] canvas').first();
  const canvasBox = (await canvas.boundingBox())!;
  const details = stack.getByRole('region', { name: 'Reference details', exact: true });
  await canvas.click({ position: { x: canvasBox.width / 2, y: canvasBox.height / 2 } });
  await expect(details).toBeVisible();
  const selected = await command('viewer-state', tabId) as CadLiveState;
  expect(selected.selection).toEqual([expect.objectContaining({ resource: expect.objectContaining({ path: 'part.step', revision }),
    target: { kind: 'cad-selector', selectors: [expect.stringMatching(/\.f\d+$/)] } })]);
  const captured = await command('capture-view', tabId) as CadLiveState & { base64: string; mimeType: string };
  expect(captured.selection).toEqual(selected.selection); expect(captured.revision).toBe(revision);
  expect(captured.mimeType).toBe('image/png'); expect(Buffer.from(captured.base64, 'base64').subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  fs.writeFileSync(test.info().outputPath('live-capture.png'), Buffer.from(captured.base64, 'base64'));
  expect((await command('cad-clear-selection', tabId) as CadLiveState).selection).toEqual([]);
  await expect(details).toHaveCount(0);
  // A lone part has no row of its own and no Parts mode, so the whole part is selected through
  // the live command; it shows its Reference the same way a pick does.
  const reselected = await command('select-reference', tabId, { selector: 'part.step' }) as CadLiveState;
  expect(reselected.selection).toEqual([expect.objectContaining({ resource: expect.objectContaining({ path: 'part.step', revision }), target: { kind: 'whole-resource' } })]);
  await expect(details).toBeVisible();
  await command('cad-clear-selection', tabId);
  const movedCamera = { ...initialCamera, position: initialCamera.position.map((value, index) => value + (index === 0 ? 5 : 0)) };
  const movedState = await command('cad-camera', tabId, { camera: movedCamera }) as CadLiveState;
  expect(movedState.display.camera).toMatchObject({ enabled: true, projection: movedCamera.projection, focalLength: movedCamera.focalLength });
  const actualCamera = await page.evaluate(() => window.__cadCamera?.());
  actualCamera!.position.forEach((value, index) => expect(value).toBeCloseTo(movedCamera.position[index]!, 5));
  const invalid = await reply('cad-camera', tabId, { camera: { ...initialCamera, position: [1, 2] } }); expect(invalid.ok).toBe(false);
  await command('cad-reset-camera', tabId);
  await expect.poll(async () => (await command('viewer-state', tabId) as CadLiveState).camera!.position[0]).not.toBeCloseTo(movedCamera.position[0]!, 2);
  const renderedState = await command('cad-render-mode', tabId, { mode: 'render' }) as CadLiveState;
  expect(renderedState.renderMode).toBe('render');
  expect(renderedState.display.mode).toBe('render');
  expect(renderedState.camera?.projection).toBe('perspective');
  // Display is the last tool on the strip; its panel leads the stack and its Mode follows the
  // live command.
  await page.locator('[data-cad-toolbar]').getByRole('button', { name: 'Display', exact: true }).click();
  const displayPanel = stack.locator('[data-tool-panel][aria-label="Display settings"]');
  await expect(displayPanel).toBeVisible();
  expect(await stack.locator('[data-tool-panel]:visible').first().getAttribute('aria-label')).toBe('Display settings');
  const displayMode = displayPanel.getByRole('combobox', { name: 'Mode', exact: true });
  await expect(displayMode).toContainText('Render');
  const solidState = await command('cad-render-mode', tabId, { mode: 'inspect' }) as CadLiveState;
  expect(solidState.display.mode).toBe('solid');
  expect(solidState.camera?.projection).toBe('orthographic');
  await expect(displayMode).toContainText('Solid');
  await page.locator('[data-tab-strip] button[aria-label="New tab"][aria-haspopup="menu"]').click();
  await page.getByRole('menuitem', { name: /^Browser/ }).click();
  await page.getByRole('tab', { name: /^New tab/ }).click();
  expect((await command('viewer-state', tabId) as CadLiveState).active).toBe(false);
  expect((await reply('cad-reset-camera', tabId)).ok).toBe(false);
  await command('show-tab', tabId);
  await expect.poll(async () => {
    const restored = await command('viewer-state', tabId) as CadLiveState;
    return restored.active && !restored.loading && restored.camera !== null;
  }).toBe(true);
  await expect(page.locator('[data-cad-surface] canvas').first()).toBeVisible();
  const restoredCapture = await command('capture-view', tabId) as CadLiveState & { mimeType: string };
  expect(restoredCapture.revision).toBe(revision); expect(restoredCapture.mimeType).toBe('image/png');
  await expect(page.locator('[data-composer] img, [data-composer] [data-reference-chip]')).toHaveCount(0);
  await expect(page.locator('[data-session-row]')).toHaveCount(1); expect(errors).toEqual([]);
});
