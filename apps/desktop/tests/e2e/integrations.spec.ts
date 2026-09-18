import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';

declare const window: { hardcore: {
  projects: { addPath(input: { path: string }): Promise<{ id: string }> };
  settings: { set(input: Record<string, unknown>): Promise<unknown> };
  sessions: {
    create(input: { projectId: string; agentId: string; gitMode: string; name: string }): Promise<{ id: string }>;
    prompt(input: { id: string; content: { type: 'text'; text: string }[] }): Promise<{ stopReason: string }>;
  };
} };
type ToolResult = { isError?: boolean; content: Array<{ type: string; text?: string; data?: string; mimeType?: string }> };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
let app: ElectronApplication, page: Page, base: string, project: string, record: string, sessionId: string;
let counter = 0;
const errors: string[] = [];

function pdfFixture() {
  const stream = 'BT /F1 16 Tf 20 100 Td (Electron PDF integration) Tj ET BT /F2 16 Tf 20 70 Td <65E5672C> Tj ET';
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R /F2 6 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type0 /BaseFont /HeiseiMin-W3 /Encoding /UniJIS-UTF16-H /DescendantFonts [7 0 R] >>',
    '<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HeiseiMin-W3 /CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) /Supplement 5 >> /FontDescriptor 8 0 R >>',
    '<< /Type /FontDescriptor /FontName /HeiseiMin-W3 /Flags 6 /FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 >>'];
  let pdf = '%PDF-1.4\n'; const offsets = [0];
  objects.forEach((object, index) => { offsets.push(pdf.length); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = pdf.length;
  return pdf + `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
}
async function proof(request: Record<string, unknown>): Promise<unknown> {
  const id = String(++counter);
  const result = await page.evaluate(({ sessionId, text }) => window.hardcore.sessions.prompt({ id: sessionId, content: [{ type: 'text', text }] }),
    { sessionId, text: `integration-proof ${JSON.stringify({ ...request, id })}` });
  expect(result.stopReason).toBe('end_turn');
  const entry = fs.readFileSync(record, 'utf8').trim().split('\n').map(line => JSON.parse(line)).find(entry => entry.kind === 'integration-proof' && entry.params.id === id);
  expect(entry, `Missing proof ${id}`).toBeDefined();
  return entry.params.result;
}
async function tool(domain: string, name: string, args: Record<string, unknown> = {}): Promise<ToolResult> {
  return await proof({ domain, name, args }) as ToolResult;
}
function json<T = Record<string, unknown>>(result: ToolResult): T {
  expect(result.isError, JSON.stringify(result)).not.toBe(true);
  const block = result.content.find(item => item.type === 'text');
  return JSON.parse(block?.text ?? '{}') as T;
}
async function readReady(tabId: string) {
  let result: ToolResult;
  for (let attempt = 0; attempt < 30; attempt++) {
    result = await tool('documents', 'read_document', { tabId });
    if (!result.isError) return json<{ content: string; revision: string; dirty: boolean; active: boolean }>(result);
    await page.waitForTimeout(100);
  }
  throw new Error('Live document did not bind.');
}

test.beforeAll(async () => {
  base = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'hardcore-integrations-e2e-')));
  project = path.join(base, 'integration-fixture'); record = path.join(base, 'agent.jsonl');
  fs.mkdirSync(project); fs.writeFileSync(path.join(project, 'notes.txt'), 'disk original\n');
  fs.writeFileSync(path.join(project, 'fixture.pdf'), pdfFixture());
  app = await electron.launch({ args: [path.join(appRoot, 'out/main/index.js'), `--user-data-dir=${path.join(base, 'profile')}`],
    env: { ...process.env, NODE_ENV: 'test', HARDCORE_E2E_HIDDEN: '1', HARDCORE_FAKE_AGENT: path.join(appRoot, 'tests/fake-agent/index.mjs'),
      FAKE_AGENT_INTEGRATION_PROOF: '1', FAKE_AGENT_RECORD: record, CADGEN_DAEMON: '0' } });
  page = await app.firstWindow(); page.on('pageerror', error => errors.push(error.message));
  await page.waitForLoadState('domcontentloaded');
  await page.evaluate(() => window.hardcore.settings.set({ theme: 'dark' }));
  const { id: projectId } = await page.evaluate(root => window.hardcore.projects.addPath({ path: root }), project);
  const session = await page.evaluate(projectId => window.hardcore.sessions.create({ projectId, agentId: 'claude-code', gitMode: 'none', name: 'Integration proof' }), projectId);
  sessionId = session.id;
  await page.locator(`[data-session-row="${sessionId}"]`).click();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
});
test.afterAll(async () => { await app?.close(); if (base) fs.rmSync(base, { recursive: true, force: true }); });

test('real ACP session starts isolated domain MCPs and operates the live app resources', async () => {
  test.setTimeout(180_000);
  const catalog = await proof({ operation: 'catalog' }) as { catalog: Array<{ name: string; tools: string[] }> };
  expect(catalog.catalog.map(entry => entry.name).sort()).toEqual(['browser', 'cad', 'documents', 'drawings', 'pdf', 'terminals', 'workspace'].map(name => `hardcore-${name}`).sort());
  expect(catalog.catalog.find(entry => entry.name === 'hardcore-documents')?.tools).toContain('edit_document');
  expect(catalog.catalog.find(entry => entry.name === 'hardcore-pdf')?.tools).not.toContain('edit_document');

  expect(catalog.catalog.find(entry => entry.name === 'hardcore-browser')?.tools).toContain('browser_snapshot');
  expect(catalog.catalog.find(entry => entry.name === 'hardcore-browser')?.tools).not.toContain('browser_connection');
  const browser = await tool('browser', 'browser_tabs', { action: 'new' });
  expect(browser.isError, JSON.stringify(browser)).not.toBe(true);
  await expect(page.getByRole('tab', { name: /about:blank/ }).last()).toBeVisible();
  const browserClosed = await proof({ operation: 'batch', domain: 'browser', calls: [
    { name: 'browser_tabs', args: { action: 'list' } }, { name: 'browser_tabs', args: { action: 'close', index: 0 } },
  ] }) as ToolResult[];
  expect(browserClosed[1]?.isError, JSON.stringify(browserClosed)).not.toBe(true);
  await expect(page.getByRole('tab', { name: /about:blank/ })).toHaveCount(0);

  const opened = json<{ tabId: string }>(await tool('workspace', 'open_file', { path: 'notes.txt' }));
  await expect(page.getByRole('tab', { name: /notes\.txt/ })).toBeVisible();
  await expect(page.locator('.monaco-editor').first()).toContainText('disk original');
  await page.locator('.monaco-editor .view-lines').first().click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
  await page.keyboard.type('human unsaved draft');
  await expect(page.getByLabel('Unsaved changes')).toBeVisible();
  let live = await readReady(opened.tabId);
  expect(live.content).toBe('human unsaved draft'); expect(live.dirty).toBe(true);
  expect(fs.readFileSync(path.join(project, 'notes.txt'), 'utf8')).toBe('disk original\n');
  const isolation = await proof({ operation: 'isolation', tabId: opened.tabId }) as { status: number };
  expect(isolation.status).toBe(403);
  const replaced = json<{ revision: string }>(await tool('documents', 'edit_document', { tabId: opened.tabId, expectedRevision: live.revision, content: 'agent reviewed draft' }));
  await expect(page.locator('.monaco-editor').first()).toContainText('agent reviewed draft');
  const stale = await tool('documents', 'edit_document', { tabId: opened.tabId, expectedRevision: live.revision, content: 'stale clobber' });
  expect(stale.isError).toBe(true); expect(stale.content[0]?.text).toMatch(/revision conflict/);
  const refused = await tool('workspace', 'close_tab', { tabId: opened.tabId });
  expect(refused.isError).toBe(true); await expect(page.getByRole('tab', { name: /notes\.txt/ })).toBeVisible();

  const drawing = json<{ tabId: string }>(await tool('drawings', 'open_drawing', { title: 'MCP scratch' }));
  expect(json(await tool('drawings', 'drawing_state', { tabId: drawing.tabId }))).toMatchObject({ elementCount: 0, ephemeral: true });
  json(await tool('drawings', 'rename_drawing', { tabId: drawing.tabId, title: 'Assembly sketch' }));
  await expect(page.getByRole('tab', { name: /Assembly sketch/ })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Drawing name' })).toHaveValue('Assembly sketch');
  live = json(await tool('documents', 'read_document', { tabId: opened.tabId }));
  expect(live).toMatchObject({ active: false, content: 'agent reviewed draft', dirty: true });
  json(await tool('workspace', 'show_tab', { tabId: opened.tabId }));
  live = await readReady(opened.tabId);
  expect(live.content).toBe('agent reviewed draft'); expect(live.revision).not.toBe(replaced.revision);
  expect(json(await tool('documents', 'save_document', { tabId: opened.tabId, expectedRevision: live.revision }))).toMatchObject({ status: 'saved' });
  expect(fs.readFileSync(path.join(project, 'notes.txt'), 'utf8')).toBe('agent reviewed draft');

  const pdf = json<{ tabId: string }>(await tool('workspace', 'open_file', { path: 'fixture.pdf' }));
  await expect(page.getByText('Electron PDF integration', { exact: true })).toBeVisible();
  expect(json(await tool('pdf', 'pdf_state', { tabId: pdf.tabId }))).toMatchObject({ page: 1, pageCount: 1, active: true });
  expect(json<{ pages: Array<{ text: string }> }>(await tool('pdf', 'read_pdf', { tabId: pdf.tabId })).pages[0]?.text).toContain('Electron PDF integration');
  expect(json<{ pages: Array<{ text: string }> }>(await tool('pdf', 'read_pdf', { tabId: pdf.tabId })).pages[0]?.text).toContain('日本');
  const capture = await tool('pdf', 'capture_pdf', { tabId: pdf.tabId });
  expect(capture.isError).not.toBe(true); expect(capture.content.find(block => block.type === 'image')?.mimeType).toBe('image/png');

  const terminal = json<{ tabId: string }>(await tool('terminals', 'create_terminal'));
  let output = json<Record<string, unknown>>(await tool('terminals', 'read_terminal', { tabId: terminal.tabId }));
  for (let attempt = 0; attempt < 10; attempt++) {
    const write = await tool('terminals', 'write_terminal', { tabId: terminal.tabId, data: 'printf "INTEGRATION_PTY_OK\\n"\n', expectedSequence: output.sequence, expectedInputRevision: output.inputRevision });
    if (!write.isError) break;
    output = json(await tool('terminals', 'read_terminal', { tabId: terminal.tabId }));
    if (attempt === 9) throw new Error(JSON.stringify(write));
  }
  await expect.poll(async () => JSON.stringify(json(await tool('terminals', 'read_terminal', { tabId: terminal.tabId })))).toContain('INTEGRATION_PTY_OK');
  json(await tool('terminals', 'stop_terminal', { tabId: terminal.tabId }));
  json(await tool('workspace', 'close_tab', { tabId: terminal.tabId }));
  json(await tool('workspace', 'close_tab', { tabId: opened.tabId }));
  await expect(page.getByRole('tab', { name: /notes\.txt/ })).toHaveCount(0);
  expect(errors).toEqual([]);
});
