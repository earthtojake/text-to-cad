import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { LOCALE_FILE, STATUS_VOCABULARY_FILE, checkUiStrings, hasWords } from './check-ui-strings.mjs';

const ENGLISH = 'export default { "tool.select": "Select", "tree.hide": "Hide" };\n';
const VOCABULARY = 'const KEYS = Object.freeze({ "Reading model": "loading.readingModel" });\n';

async function fixture(files, allowlist = []) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'text-to-cad-ui-strings-'));
  for (const [name, code] of Object.entries({ [LOCALE_FILE]: ENGLISH, [STATUS_VOCABULARY_FILE]: VOCABULARY, ...files })) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, code);
  }
  try { return await checkUiStrings(root, { allowlist }); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

test('a view that says everything through t passes, and so does what is no language', async () => {
  assert.deepEqual(await fixture({
    'packages/ui/src/a.jsx': 'export const A = ({ t, open }) => <button aria-label={t("tree.hide")} title={open ? t("tree.hide") : t("tool.select")}>{t("tool.select")} STEP · mm · Ctrl+C</button>;\n',
    'apps/web/src/b.ts': 'export const formats = [{ id: "step", label: "STEP" }, { id: "brand", label: "GitHub" }];\n',
  }), []);
});

test('English in JSX text, a read attribute, a child, an object label or a toast fails, in every tree', async () => {
  const errors = await fixture({
    'packages/ui/src/a.jsx': 'export const A = ({ open, name }) => <div aria-label={`Close ${name}`}><span title="Hide">Show all</span>{open ? "Collapse" : "Expand"}</div>;\n',
    'apps/mcp/src/b.ts': 'export const tool = { id: "select", label: "Select" };\n',
    'apps/web/src/c.ts': 'import { toast } from "sonner";\nexport const done = () => toast.error("Export failed");\n',
  });
  assert.deepEqual(errors.map(error => error.split(' ').slice(0, 2).join(' ')), [
    'packages/ui/src/a.jsx:1 aria-label=', 'packages/ui/src/a.jsx:1 title=', 'packages/ui/src/a.jsx:1 JSX',
    'packages/ui/src/a.jsx:1 JSX', 'packages/ui/src/a.jsx:1 JSX', 'apps/web/src/c.ts:2 toast.error()', 'apps/mcp/src/b.ts:1 label:',
  ]);
});

test('a keyed table entry, a progress record and a status vocabulary line pass; a missing key fails', async () => {
  const errors = await fixture({
    'packages/ui/src/a.js': [
      'export const MODES = [{ value: "solid", key: "mode.solid", label: "Solid" }];',
      'export const step = { phase: "read", label: "Opening document" };',
      'export const status = { pending: true, label: "Reading model" };',
      'export const said = t => t("no.such.key");',
    ].join('\n'),
  });
  assert.deepEqual(errors, ['packages/ui/src/a.js:4 t() names a key en.js does not have: "no.such.key"']);
});

test('tests, fixtures and the test harnesses are not read; an exception says what it says', async () => {
  assert.deepEqual(await fixture({
    'packages/ui/src/a.test.jsx': 'export const A = () => <p>Hello there</p>;\n',
    'packages/ui/src/renderers/shell-harness/H.jsx': 'export const H = () => <p>Harness only</p>;\n',
    'packages/ui/src/b.js': 'export const fail = () => { throw new Error("The viewer is not ready"); };\n',
  }), []);
});

test('an allow-list line excuses its text in its file only, and a line that excuses nothing fails', async () => {
  const files = { 'packages/ui/src/a.js': 'export const view = { label: "current view" };\n', 'packages/ui/src/b.js': 'export const view = { label: "current view" };\n' };
  const errors = await fixture(files, [['packages/ui/src/a.js', 'current view', 'the prompt names it'], ['packages/ui/src/c.js', 'gone', 'stale']]);
  assert.deepEqual(errors, [
    'packages/ui/src/b.js:1 label: "current view"',
    'UI_STRINGS_ALLOWLIST line for packages/ui/src/c.js ("gone") matches nothing: delete it',
  ]);
});

test('words are two letters running that are not a format, unit, brand or key chord', () => {
  for (const text of ['Select', 'Close ${}', 'Measurement ${}: ${}']) assert.equal(hasWords(text), true, text);
  for (const text of ['STEP', 'mm²', 'GitHub', 'Shift+', 'Ctrl+C', '×', '${} × ${}', 'X', '', null]) assert.equal(hasWords(text), false, String(text));
});
