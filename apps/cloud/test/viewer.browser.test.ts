/**
 * A build in the viewer, end to end: a small project exported by the real `cadgen viewer export`
 * (`exportFixture.py`, its STEP trees seeded without the kernel), served by `serveExport.mjs` —
 * the built page, the compat viewer API over the export, the objects — and opened in a real
 * Chromium. Every view must draw from the export alone, with no failed request and no page
 * error, and a picked face must be copied as a URL reference.
 *
 * Needs the built page (`npm --prefix apps/cloud run build`) and a Python with cadgen
 * (`CLOUD_PYTHON`, else the repo's `.venv`); it fails loudly without either.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { Browser, Page } from 'playwright';
import { startExportServer } from './serveExport.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../../..');
const APP = path.resolve(HERE, '..');
const { chromium } = createRequire(path.join(REPO, 'packages/core/package.json'))('playwright') as typeof import('playwright');
const BUILD = 'k7Qx2';
const TIMEOUT = 90_000;

function pythonWithCadgen(): string {
  const named = String(process.env.CLOUD_PYTHON || '').trim();
  const candidates = [named, path.join(REPO, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')].filter(Boolean);
  const found = candidates.find(candidate => fs.existsSync(candidate));
  if (!found) throw new Error(`no Python with cadgen: set CLOUD_PYTHON (tried ${candidates.join(', ')})`);
  return found;
}

/** The staged model's bounds, from whichever seam its renderer publishes (as `tests/browser/viewer-e2e.mjs` reads them). */
const MODEL_BOUNDS_SCRIPT = `window.__cadModelBounds = () => {
  const placement = window.__cadModelPlacement;
  if (Array.isArray(placement?.boundsMin)) return { min: placement.boundsMin, max: placement.boundsMax };
  const stage = window.__cadStage?.();
  return stage?.bounds ? { min: stage.bounds.min, max: stage.bounds.max } : null;
};
window.__copied = [];
const record = text => { window.__copied.push(String(text)); };
Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
  writeText: async text => record(await text),
  write: async items => { for (const item of items) record(item.types.includes('text/plain') ? await (await item.getType('text/plain')).text() : '[' + item.types.join(',') + ']'); },
  readText: async () => window.__copied.at(-1) || '',
} });`;

interface Opened { page: Page; failures: string[]; close(): Promise<void> }

describe('a build in the viewer', () => {
  let work = '';
  let server: Awaited<ReturnType<typeof startExportServer>>;
  let browser: Browser;
  let views: string[] = [];

  beforeAll(async () => {
    if (!fs.existsSync(path.join(APP, 'dist/index.html'))) throw new Error('build the page first: npm --prefix apps/cloud run build');
    work = fs.mkdtempSync(path.join(os.tmpdir(), 'cloud-viewer-'));
    const project = path.join(work, 'project'), out = path.join(work, 'export');
    const summary = JSON.parse(execFileSync(pythonWithCadgen(), [path.join(HERE, 'exportFixture.py'), project, out], {
      encoding: 'utf8', env: { ...process.env, CADGEN_CACHE_DIR: path.join(work, 'store'), CADGEN_DAEMON: '0', CADGEN_STATE_DIR: path.join(work, 'state') },
    }));
    expect(summary.ok).toBe(true);
    views = summary.views;
    server = await startExportServer({ exportDir: out, rootDir: project, id: BUILD });
    const angle = process.platform === 'darwin' && process.env.CAD_TEST_SWIFTSHADER !== '1' ? 'metal' : 'swiftshader';
    browser = await chromium.launch({ headless: true, args: [`--use-angle=${angle}`, '--ignore-gpu-blocklist', ...(angle === 'swiftshader' ? ['--enable-unsafe-swiftshader'] : [])] });
  }, TIMEOUT);

  afterAll(async () => {
    await browser?.close();
    await server?.close();
    if (work) fs.rmSync(work, { recursive: true, force: true });
  });

  async function open(file: string): Promise<Opened> {
    const context = await browser.newContext({ viewport: { width: 1024, height: 640 }, deviceScaleFactor: 1 });
    const failures: string[] = [];
    const page = await context.newPage();
    page.on('response', response => {
      const url = response.url();
      // The build's API and its objects must answer; a redirect is an answer.
      if (response.status() >= 400 && (url.includes('/__cad/') || url.includes('/__tess_cache/') || url.includes('/o/'))) failures.push(`HTTP ${response.status()} ${response.request().method()} ${url}`);
    });
    page.on('requestfailed', request => { if (!request.url().includes('/__tess_cache/') && request.failure()?.errorText !== 'net::ERR_ABORTED') failures.push(`failed ${request.method()} ${request.url()}: ${request.failure()?.errorText}`); });
    page.on('pageerror', error => failures.push(`page: ${error.message}`));
    page.on('console', message => { if (message.type() === 'error') failures.push(`console: ${message.text()}`); });
    await page.addInitScript(MODEL_BOUNDS_SCRIPT);
    await page.goto(`${server.url}/b/${BUILD}${file}`, { waitUntil: 'domcontentloaded' });
    await page.locator('[data-slot="cad-file-view"]').first().waitFor({ timeout: 60_000 });
    await page.locator('[data-slot="cad-file-view"] [aria-busy="false"]').first().waitFor({ timeout: 60_000 });
    if (!/\.dxf$/i.test(file)) {
      await page.waitForFunction(() => {
        const bounds = (window as unknown as { __cadModelBounds?: () => { min: number[]; max: number[] } | null }).__cadModelBounds?.();
        return Array.isArray(bounds?.min) && Array.isArray(bounds?.max) && bounds.min.some((value, axis) => Number(bounds.max[axis]) - Number(value) > 0);
      }, null, { timeout: 60_000 });
    }
    return { page, failures, close: () => context.close() };
  }

  it('draws every exported file from the export alone, with nothing failing', async () => {
    expect(views).toEqual(['/DXF/plate.dxf', '/STEP/bracket.step', '/STEP/pair.step', '/meshes/tetra.stl', '/robot.urdf']);
    for (const file of views) {
      const opened = await open(file);
      try {
        expect(await opened.page.title()).toBe(`CAD | ${file.split('/').pop()}`);
        expect(await opened.page.locator('[data-cloud-host-bar] [data-build-id]').textContent()).toBe(BUILD);
        expect(opened.failures, file).toEqual([]);
      } finally { await opened.close(); }
    }
  }, TIMEOUT);

  it('names a picked part by the file’s URL, in the Reference panel’s copy and in Quick Edit', async () => {
    const opened = await open('/STEP/pair.step');
    try {
      const { page } = opened;
      const canvas = page.locator('[data-slot="cad-file-view"] canvas').first();
      const box = await canvas.boundingBox();
      if (!box) throw new Error('no viewport');
      // The right-hand box of the pair sits right of centre; a press on it selects that part.
      await page.mouse.click(box.x + box.width * 0.66, box.y + box.height * 0.58);
      const copy = page.getByRole('button', { name: /^Copy(?: All)?$/ });
      await copy.first().waitFor({ timeout: 20_000 });
      await copy.first().click();
      const address = `${server.url}/b/${BUILD}/STEP/pair.step`;
      await page.waitForFunction(() => (window as unknown as { __copied: string[] }).__copied.length > 0, null, { timeout: 10_000 });
      const reference = await page.evaluate(() => (window as unknown as { __copied: string[] }).__copied.at(-1));
      expect(reference).toMatch(new RegExp(`^${address.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}#o1\\.\\d+$`));
      const note = page.getByRole('textbox', { name: 'Describe your changes' });
      await note.fill('Make this taller.');
      await page.getByRole('button', { name: 'Copy Prompt' }).click();
      await page.waitForFunction(() => (window as unknown as { __copied: string[] }).__copied.length > 1, null, { timeout: 10_000 });
      const prompt = await page.evaluate(() => (window as unknown as { __copied: string[] }).__copied.at(-1));
      expect(prompt).toBe(`Make this taller.\n\nFile: ${address}\nReferences:\n${reference}`);
      expect(opened.failures).toEqual([]);
    } finally { await opened.close(); }
  }, TIMEOUT);
});
