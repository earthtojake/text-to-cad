import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  checkFileViewerBoundary, checkKitBoundaries, checkRendererSlices, checkSharedSceneBuilders, FILE_VIEWER_ROOT, HEADLESS_ENTRY, HEADLESS_SCENE,
  KIT_ROOT, RENDERERS_ROOT, SHARED_SCENE_PIECES
} from './check-kit-boundaries.mjs';

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
  [kit('tools/a.js')]: "import x from '../../step/workbench/state.js';\n",
  [kit('tools/b.js')]: "const load = () => import('@hardcore/core/lib/urdf/parseUrdf.js');\n",
  [kit('tools/c.js')]: "import { buildModel } from '@hardcore/core/common/cadScene.js';\n",
  [kit('tools/d.js')]: "import y from '@hardcore/ui/renderers/step';\n",
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

function sliceFixture(files, run) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hardcore-renderer-slices-'));
  for (const [name, code] of Object.entries(files)) {
    const file = path.join(root, RENDERERS_ROOT, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, code);
  }
  try { run(checkRendererSlices(root, { slices: ['glb'] })); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

test('a renderer slice imports the kit, the workspace module, shared UI and core', () => sliceFixture({
  'glb/index.ts': "import { defineFileRenderer } from '../../file-viewer/registry.js';\nimport { prepareWorkspaceEntry } from '../workspace/index.js';\nimport Shell from '../kit/shell/RendererShell.jsx';\nimport { x } from '@hardcore/core/lib/entryAssets.js';\nimport { scene } from './glbScene.js';\nconst load = () => import('./GlbRenderer.jsx');\n",
}, result => assert.deepEqual(result.errors, [])));

test('a renderer slice never imports another renderer; its tests are not scanned', () => sliceFixture({
  'glb/a.js': "import view from '../step/file-view/StepSurface.jsx';\n",
  'glb/b.js': "const load = () => import('@hardcore/ui/renderers/step');\n",
  'glb/c.test.js': "import '../step/live.js';\n",
}, result => {
  assert.equal(result.errors.length, 2);
  assert.ok(result.errors.every(error => error.includes('imports the "step" renderer')));
}));

test('a listed slice that does not exist fails rather than passing silently', () => sliceFixture({
  'mesh/index.ts': "export {};\n",
}, result => assert.match(result.errors[0], /does not exist/)));

function hostFixture(files, run) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hardcore-file-viewer-boundary-'));
  for (const [name, code] of Object.entries(files)) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, code);
  }
  try { run(checkFileViewerBoundary(root)); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const host = name => `${FILE_VIEWER_ROOT}/${name}`;

test('the file viewer builds its own chrome out of the kit', () => hostFixture({
  [host('EmptyCadStage.tsx')]: "import Viewport from '../renderers/kit/shell/ShellViewport.jsx';\nimport { prepareWorkspaceEntry } from '../renderers/workspace/prepare.js';\nimport { cn } from '@hardcore/ui/utils';\n",
}, result => assert.deepEqual(result.errors, [])));

test('the file viewer never imports a family slice: it mounts one through the registry', () => hostFixture({
  [host('empty.tsx')]: "const Stage = () => import('../renderers/step/components/EmptyCadStage.js');\n",
  [host('navigation/icons.ts')]: "import { GLB } from '@hardcore/ui/renderers/glb';\n",
  [host('empty.test.tsx')]: "import '../renderers/robot/RobotRenderer.jsx';\n",
}, result => {
  assert.equal(result.errors.length, 2, 'both sources are caught and the test file is not scanned');
  assert.ok(result.errors.some(error => error.includes('imports the "step" renderer')));
  assert.ok(result.errors.some(error => error.includes('imports the "glb" renderer')));
}));

test('a missing file viewer fails rather than passing silently', () => hostFixture({
  'packages/ui/src/renderers/kit/shell/ShellViewport.jsx': "export default null;\n",
}, result => assert.match(result.errors[0], /does not exist/)));

// A repository in which every shared scene piece is imported by the viewer AND the snapshot
// from its one module, defined there and nowhere else; `patch` breaks one thing at a time.
function sharedFixture(patch, run) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hardcore-shared-scenes-'));
  const files = {};
  const coreSpecifier = module => `@hardcore/core/${module.replace('packages/core/src/', '')}`;
  const relativeTo = (from, module) => {
    const rel = path.relative(path.dirname(from), module).split(path.sep).join('/');
    return rel.startsWith('.') ? rel : `./${rel}`;
  };
  const headless = [];
  for (const piece of SHARED_SCENE_PIECES) {
    const names = [...new Set([...piece.viewer[1], ...piece.headless])];
    files[piece.module] = `${files[piece.module] || ''}${names.map(name => `export function ${name}() {}\n`).join('')}`;
    files[piece.viewer[0]] = `${files[piece.viewer[0]] || ''}import { ${piece.viewer[1].join(', ')} } from '${coreSpecifier(piece.module)}';\n`;
    headless.push(`import {\n  ${piece.headless.join(',\n  ')}\n} from '${relativeTo(HEADLESS_SCENE, piece.module)}';`);
  }
  // The two builders the others are made of: defined once, called through the pieces above.
  files['packages/core/src/lib/render/meshScene.js'] += 'export function createMeshScene() {}\n';
  files['packages/core/src/lib/urdf/robotParts.js'] = 'export function buildRobotParts() {}\n';
  files[HEADLESS_SCENE] = `${headless.join('\n')}\nexport function headlessSceneFamily() {}\n`;
  files[HEADLESS_ENTRY] = "import { headlessSceneFamily, headlessSceneModel } from './headlessScene.js';\n";
  patch(files);
  for (const [name, code] of Object.entries(files)) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, code);
  }
  try { run(checkSharedSceneBuilders(root)); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

test('the viewer and the snapshot build each family from one shared module', () => sharedFixture(() => {},
  result => assert.deepEqual(result.errors, [])));

test('a snapshot that draws a family with a builder of its own is refused', () => sharedFixture((files) => {
  files[HEADLESS_SCENE] = files[HEADLESS_SCENE].replace("from '../lib/render/glbScene.js'", "from './glbSnapshotScene.js'");
  files['packages/core/src/common/glbSnapshotScene.js'] = 'export function createGlbScene() {}\n';
}, result => {
  assert.ok(result.errors.some(error => error.includes("the GLB scene: the snapshot's") && error.includes('./glbSnapshotScene.js')), result.errors.join('\n'));
  assert.ok(result.errors.some(error => error.startsWith('createGlbScene is defined in 2 places')), result.errors.join('\n'));
}));

test('a viewer renderer that builds its own scene is refused as well', () => sharedFixture((files) => {
  files['packages/ui/src/renderers/robot/RobotRenderer.jsx'] = 'function createRobotScene() {}\n';
}, result => assert.deepEqual(result.errors.sort(), [
  "createRobotScene is defined in 2 places (packages/core/src/lib/urdf/robotScene.js, packages/ui/src/renderers/robot/RobotRenderer.jsx); it is ONE shared builder",
  "the robot scene: the viewer's packages/ui/src/renderers/robot/RobotRenderer.jsx does not import createRobotScene"
])));

test('the snapshot entry routes families through the shared scenes and reaches for no mesh flattener', () => sharedFixture((files) => {
  files[HEADLESS_ENTRY] = "import { buildModel } from './cadScene.js';\n";
  files['packages/core/src/common/source.js'] = "import { buildMeshDataFromGlbBuffer } from '../lib/render/glbMeshData.js';\n";
}, result => assert.deepEqual(result.errors, [
  `${HEADLESS_ENTRY} does not route a family's job through headlessSceneFamily (${HEADLESS_SCENE})`,
  'packages/core/src/common/source.js imports buildMeshDataFromGlbBuffer: the snapshot draws a family with its shared builder, never a copy flattened for it'
])));
