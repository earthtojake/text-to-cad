import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { checkKitBoundaries, KIT_ROOT } from './check-kit-boundaries.mjs';

function fixture(files, run, allowlist = []) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hardcore-kit-boundaries-'));
  for (const [name, code] of Object.entries(files)) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, code);
  }
  try { run(checkKitBoundaries(root, { allowlist })); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const kit = name => `${KIT_ROOT}/${name}`;

test('a format-blind kit module passes, including its shared-UI and core imports', () => fixture({
  [kit('camera/fit.js')]: "import { cn } from '@hardcore/ui/utils';\nimport { mergeBoundsList } from '@hardcore/core/lib/viewer/autoZoom.js';\nimport { other } from '../viewport/other.js';\nimport { fuzzy } from '../../../file-viewer/navigation/fuzzy.js';\nexport const stepKeyboardOrbit = () => document.querySelector('canvas');\n",
}, result => assert.deepEqual(result.errors, [])));

test('the kit never imports a renderer or a file-family core module', () => fixture({
  [kit('tools/a.js')]: "import x from '../../cad/workbench/state.js';\n",
  [kit('tools/b.js')]: "const load = () => import('@hardcore/core/lib/urdf/parseUrdf.js');\n",
  [kit('tools/c.js')]: "import { buildModel } from '@hardcore/core/common/cadScene.js';\n",
  [kit('tools/d.js')]: "import y from '@hardcore/ui/renderers/cad';\n",
}, result => {
  assert.equal(result.errors.filter(error => error.includes('imports a renderer')).length, 2);
  assert.equal(result.errors.filter(error => error.includes('file-family core module')).length, 2);
}));

test('format and STEP-assembly words are refused in code and in comments; tests are not scanned', () => fixture({
  [kit('look/a.js')]: "// the DXF material catalog\nexport const a = 1;\n",
  [kit('look/b.js')]: "export const b = renderFormat === 'x';\n",
  [kit('look/c.js')]: "export const c = entry => entry.selectorRuntime;\n",
  [kit('look/d.js')]: "export const normalizeStepThing = 1;\n",
  [kit('look/e.js')]: "export const explodedView = 1;\n",
  [kit('look/e.test.js')]: "import '../../cad/x.js'; const glb = 'STEP';\n",
}, result => assert.deepEqual(result.errors.map(error => error.split(' names ')[1]?.split(':')[0]).sort(),
  ['STEP', 'a file format', 'a file-kind switch', 'explode', 'selectors'])));

test('view-settings may name its opt-in Clip and Explode sections, and nothing else', () => fixture({
  [kit('view-settings/tab.js')]: "export const sections = ['clip', 'exploded']; const clipBounds = null; // Explode\n",
  [kit('view-settings/bad.js')]: "export const topologyEdges = 1;\n",
}, result => assert.deepEqual(result.errors.map(error => error.split(' names ')[1]?.split(':')[0]), ['topology'])));

test('an allowlist entry excuses exactly its line and goes stale when the line leaves', () => fixture({
  [kit('camera/control.js')]: "const label = 'Perspective selector';\n",
}, result => assert.deepEqual(result.errors, ['stale kit allowlist entry: camera/gone.js "selector"']),
[['camera/control.js', 'Perspective selector', 'a UI word'], ['camera/gone.js', 'selector', 'left over']]));
