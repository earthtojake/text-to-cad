#!/usr/bin/env node
// The renderer kit (packages/ui/src/renderers/kit) is format-blind: it never asks
// what it is showing. Two rules, enforced over its non-test sources:
//
//   1. IMPORTS. The kit imports itself, shared UI (primitives, lib, drawing,
//      file-viewer navigation helpers) and the format-blind half of
//      @hardcore/core. It never imports a renderer, and never a core module that
//      belongs to one file family. Renderers import the kit; never the reverse.
//   2. WORDS. No file-format or STEP-assembly concept appears in it, in code or in
//      comments: a comment that explains a kit module by naming a format is the
//      first sign the module knows about that format.
//
// The Display settings model may name the Edges, Clip and Explode SECTIONS: a view
// opts into them by list (`ViewFeatures`), and the kit does not know who opts in.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const KIT_ROOT = 'packages/ui/src/renderers/kit';

// Core modules that belong to one file family, or to the STEP assembly pipeline.
const FAMILY_CORE_IMPORT = /^@hardcore\/core\/(?:glb\/|lib\/(?:assembly|dxf|export|glb|render|selectors|step|surf|urdf)\/|lib\/(?:cadRefs|entryAssets|fileFormats|renderCapabilities|renderAssetClient|stepRenderAssetClient)\.js|common\/(?:cadScene|renderMeshScene|stepModule\w*|topology\w*|applySceneState)\.js)/;

const FORBIDDEN_WORDS = [
  ['a file format', /urdf|srdf|(?<![a-z])sdf(?![a-z])|glb|gltf|dxf|(?<![a-z])stl(?![a-z])|3mf|b-?rep(?![a-z])/i],
  ['STEP', /(?<![A-Za-z])STEP(?![A-Za-z])|Step[A-Z]|\bstep(?:Module|Tree|File|Reference|Artifact|Topology|Selection|Geometry|Animation|Pose|Motion|Clip)|["'`]step["'`]|\bisStep\b/],
  ['a file-kind switch', /renderFormat|fileKind|sourceFormat|sheetKind|cadModel|\bformat\s*[!=]==|\brobot/i],
  ['topology', /topolog/i],
  ['selectors', /(?<!query)selector/i],
  ['STEP display records', /displayRecord/],
  ['explode', /explod/i],
  ['section clipping', /clipplane(?!s)|sectioncap|clip(?:settings|bounds|axis|offset)/i],
];

// The view-settings model names its opt-in sections (rule above). `edges` is not a
// forbidden word anywhere; these two are, outside this folder.
const SECTION_WORDS_ALLOWED_IN = `${KIT_ROOT}/view-settings/`;
const SECTION_RULES = new Set(['explode', 'section clipping']);

// Every other exception, one line each: [file under the kit, text on the line, why].
export const KIT_WORD_ALLOWLIST = [
  ['camera/ViewPlaneControl.js', 'showSelector', 'UI word: the view-plane "selector" is the orientation control itself, not a CAD selector'],
  ['view-settings/viewerDisplaySettings.js', 'buildStepClipPatch', "core's clip-settings API carries STEP in its names; the settings model only passes the Clip section through"],
];

function kitSources(dir, out = []) {
  for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, item.name);
    if (item.isDirectory()) kitSources(file, out);
    else if (/\.[cm]?[jt]sx?$/.test(item.name) && !/\.(test|spec)\./.test(item.name)) out.push(file);
  }
  return out;
}

export function checkKitBoundaries(repo, { allowlist = KIT_WORD_ALLOWLIST } = {}) {
  const root = path.join(repo, KIT_ROOT);
  const errors = [];
  const used = new Set();
  const renderers = path.join(repo, 'packages/ui/src/renderers') + path.sep;
  const files = fs.existsSync(root) ? kitSources(root) : [];
  for (const file of files) {
    const rel = path.relative(root, file).split(path.sep).join('/');
    const repoRel = `${KIT_ROOT}/${rel}`;
    const lines = fs.readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, index) => {
      const at = `${repoRel}:${index + 1}`;
      for (const match of line.matchAll(/(?:from\s*|import\s*\(\s*|import\s+|new URL\(\s*)["']([^"']+)["']/g)) {
        const specifier = match[1];
        if (specifier.startsWith('.')) {
          const target = path.resolve(path.dirname(file), specifier);
          if (target.startsWith(renderers) && !target.startsWith(root + path.sep)) errors.push(`${at} imports a renderer (${specifier}); renderers import the kit, never the reverse`);
          if (!target.startsWith(path.join(repo, 'packages/ui/src') + path.sep)) errors.push(`${at} imports outside @hardcore/ui sources (${specifier})`);
        } else if (/^@hardcore\/ui\/renderers\//.test(specifier)) errors.push(`${at} imports a renderer (${specifier})`);
        else if (FAMILY_CORE_IMPORT.test(specifier)) errors.push(`${at} imports a file-family core module (${specifier})`);
      }
      for (const [rule, pattern] of FORBIDDEN_WORDS) {
        if (!pattern.test(line)) continue;
        if (SECTION_RULES.has(rule) && repoRel.startsWith(SECTION_WORDS_ALLOWED_IN)) continue;
        const allowed = allowlist.findIndex(([allowedFile, text]) => allowedFile === rel && line.includes(text));
        if (allowed >= 0) { used.add(allowed); continue; }
        errors.push(`${at} names ${rule}: ${line.trim().slice(0, 120)}`);
      }
    });
  }
  allowlist.forEach(([file, text], index) => { if (!used.has(index)) errors.push(`stale kit allowlist entry: ${file} "${text}"`); });
  return { errors, sourceCount: files.length };
}

// RENDERER SLICES. One renderer per file family, each a vertical slice: it imports
// the kit, the shared workspace module (backend connection, preferences), shared
// UI and core. It never imports another renderer, so a family can be changed,
// lazy-loaded and deleted alone. Every file family is on this list; `workspace`
// is held to the same rule.
export const RENDERERS_ROOT = 'packages/ui/src/renderers';
export const RENDERER_SLICES = ['dxf', 'glb', 'mesh', 'robot', 'step', 'workspace'];
const SLICE_SHARED = ['kit', 'workspace'];

export function checkRendererSlices(repo, { slices = RENDERER_SLICES } = {}) {
  const renderers = path.join(repo, RENDERERS_ROOT);
  const errors = [];
  let sourceCount = 0;
  for (const slice of slices) {
    const root = path.join(renderers, slice);
    if (!fs.existsSync(root)) { errors.push(`renderer slice "${slice}" is listed but ${RENDERERS_ROOT}/${slice} does not exist`); continue; }
    for (const file of kitSources(root)) {
      sourceCount += 1;
      const repoRel = path.relative(repo, file).split(path.sep).join('/');
      fs.readFileSync(file, 'utf8').split('\n').forEach((line, index) => {
        for (const match of line.matchAll(/(?:from\s*|import\s*\(\s*|import\s+|new URL\(\s*)["']([^"']+)["']/g)) {
          const specifier = match[1];
          let owner = '';
          if (specifier.startsWith('.')) {
            const target = path.resolve(path.dirname(file), specifier);
            if (target.startsWith(renderers + path.sep)) owner = path.relative(renderers, target).split(path.sep)[0];
          } else owner = /^@hardcore\/ui\/renderers\/([^/]+)/.exec(specifier)?.[1] || '';
          if (owner && owner !== slice && !SLICE_SHARED.includes(owner)) {
            errors.push(`${repoRel}:${index + 1} imports the "${owner}" renderer (${specifier}); a renderer imports the kit, the workspace module, shared UI and core, never another renderer`);
          }
        }
      });
    }
  }
  return { errors, sourceCount };
}

// THE HOST'S FILE VIEWER. `packages/ui/src/file-viewer` is what MOUNTS a renderer: it
// resolves which slice a file belongs to and lazy-loads it through the registry. So it must
// not import one itself — a static edge into a slice defeats the split, pulling that
// family's code (and three.js with it) into every host that shows any file at all. The kit
// and the workspace module are shared, so those are fine. The empty CAD backdrop is the case
// this rule was written for: it drew a stage with NO model in it and reached into the STEP
// renderer to do it.
export const FILE_VIEWER_ROOT = 'packages/ui/src/file-viewer';

export function checkFileViewerBoundary(repo, { shared = SLICE_SHARED } = {}) {
  const root = path.join(repo, FILE_VIEWER_ROOT);
  const renderers = path.join(repo, RENDERERS_ROOT);
  if (!fs.existsSync(root)) return { errors: [`${FILE_VIEWER_ROOT} does not exist`], sourceCount: 0 };
  const errors = [];
  const files = kitSources(root);
  for (const file of files) {
    const repoRel = path.relative(repo, file).split(path.sep).join('/');
    fs.readFileSync(file, 'utf8').split('\n').forEach((line, index) => {
      for (const match of line.matchAll(/(?:from\s*|import\s*\(\s*|import\s+|new URL\(\s*)["']([^"']+)["']/g)) {
        const specifier = match[1];
        let owner = '';
        if (specifier.startsWith('.')) {
          const target = path.resolve(path.dirname(file), specifier);
          if (target.startsWith(renderers + path.sep)) owner = path.relative(renderers, target).split(path.sep)[0];
        } else owner = /^@hardcore\/ui\/renderers\/([^/]+)/.exec(specifier)?.[1] || '';
        if (owner && !shared.includes(owner)) {
          errors.push(`${repoRel}:${index + 1} imports the "${owner}" renderer (${specifier}); the file viewer mounts a renderer through the registry and imports only the kit and the workspace module`);
        }
      }
    });
  }
  return { errors, sourceCount: files.length };
}

// ONE SCENE BUILDER PER FILE FAMILY, TWO CALLERS. The snapshot CLI's headless stage
// (`HEADLESS_SCENE`) and the viewer's renderer for a family draw that family's files with
// the same core module: the same loader, the same builder, the same look and the same
// opening pose. So each shared piece is imported by BOTH from ONE module, is defined
// nowhere else, and the headless render path imports no mesh flattener of its own — a
// snapshot that drew a GLB, a mesh or a robot its own way is exactly what this stops.
export const HEADLESS_ENTRY = 'packages/core/src/common/headlessRenderEntry.js';
export const HEADLESS_SCENE = 'packages/core/src/common/headlessScene.js';
export const SHARED_SCENE_PIECES = [
  { what: 'the GLB scene', module: 'packages/core/src/lib/render/glbScene.js',
    viewer: ['packages/ui/src/renderers/glb/useGlbScene.js', ['createGlbScene']], headless: ['createGlbScene'] },
  { what: 'the mesh scene', module: 'packages/core/src/lib/render/meshScene.js',
    viewer: ['packages/ui/src/renderers/mesh/useMeshScene.js', ['buildMeshScene']], headless: ['buildMeshScene'] },
  { what: 'the robot scene', module: 'packages/core/src/lib/urdf/robotScene.js',
    viewer: ['packages/ui/src/renderers/robot/RobotRenderer.jsx', ['createRobotScene']], headless: ['createRobotScene'] },
  { what: 'the robot loader', module: 'packages/core/src/lib/urdf/loadRobot.js',
    viewer: ['packages/ui/src/renderers/robot/useRobotDocument.js', ['loadRobotDescription', 'loadRobotMeshes', 'robotModel']], headless: ['loadRobot'] },
  { what: 'the opening pose', module: 'packages/core/src/lib/urdf/motion.js',
    viewer: ['packages/ui/src/renderers/robot/poseStore.js', ['robotOpeningPose']], headless: ['robotOpeningPose'] },
  { what: 'the surface look', module: 'packages/core/src/common/sceneSettings.js',
    viewer: ['packages/ui/src/renderers/kit/shell/ShellViewport.jsx', ['resolveSceneSurfaceLook']], headless: ['resolveSceneSurfaceLook'] },
];
// Defined once, in their module: a second definition is a second way to draw a family.
const SHARED_BUILDER_NAMES = ['createGlbScene', 'createMeshScene', 'buildMeshScene', 'createRobotScene', 'buildRobotParts',
  'robotOpeningPose', 'resolveSceneSurfaceLook'];
// What the headless render path used to flatten a family with, and must not reach for again.
const HEADLESS_RENDER_PATH = [HEADLESS_ENTRY, HEADLESS_SCENE, 'packages/core/src/common/renderMeshScene.js', 'packages/core/src/common/source.js'];
const MESH_FLATTENERS = ['buildMeshDataFromGlbBuffer', 'buildMeshDataFromStlBuffer', 'buildMeshDataFrom3MfBuffer', 'buildUrdfVisualParts', 'buildRobotParts'];

// `import { a, b as c } from '...'` (across lines): each imported NAME with the specifier it came from.
function namedImports(code) {
  const imports = [];
  for (const match of code.matchAll(/import\s*\{([^}]*)\}\s*from\s*["']([^"']+)["']/g)) {
    for (const part of match[1].split(',')) {
      const name = part.trim().split(/\s+as\s+/)[0].trim();
      if (name) imports.push({ name, specifier: match[2] });
    }
  }
  return imports;
}

function resolveSource(repo, file, specifier) {
  const core = /^@hardcore\/core\/(lib|common)\/(.+)$/.exec(specifier);
  if (core) return `packages/core/src/${core[1]}/${core[2]}`;
  if (specifier.startsWith('.')) return path.relative(repo, path.resolve(path.dirname(path.join(repo, file)), specifier)).split(path.sep).join('/');
  return specifier;
}

function packageSources(repo) {
  const files = [];
  for (const root of ['packages/core/src', 'packages/ui/src']) {
    const dir = path.join(repo, root);
    if (!fs.existsSync(dir)) continue;
    for (const file of kitSources(dir)) {
      const rel = path.relative(repo, file).split(path.sep).join('/');
      if (!rel.split('/').some(part => part === '__tests__' || part === 'harness')) files.push(rel);
    }
  }
  return files;
}

export function checkSharedSceneBuilders(repo, { pieces = SHARED_SCENE_PIECES, builderNames = SHARED_BUILDER_NAMES } = {}) {
  const errors = [];
  const read = rel => (fs.existsSync(path.join(repo, rel)) ? fs.readFileSync(path.join(repo, rel), 'utf8') : null);
  const importsFrom = (rel, names, module) => {
    const code = read(rel);
    if (code === null) return `${rel} does not exist`;
    const found = namedImports(code).filter(entry => names.includes(entry.name));
    const missing = names.filter(name => !found.some(entry => entry.name === name));
    if (missing.length) return `${rel} does not import ${missing.join(', ')}`;
    const elsewhere = found.filter(entry => resolveSource(repo, rel, entry.specifier) !== module);
    return elsewhere.length ? `${rel} imports ${elsewhere.map(entry => `${entry.name} from ${entry.specifier}`).join(', ')}, not from ${module}` : '';
  };
  for (const piece of pieces) {
    if (read(piece.module) === null) { errors.push(`${piece.what}: ${piece.module} does not exist`); continue; }
    const [viewerFile, viewerNames] = piece.viewer;
    const viewer = importsFrom(viewerFile, viewerNames, piece.module);
    if (viewer) errors.push(`${piece.what}: the viewer's ${viewer}`);
    const headless = importsFrom(HEADLESS_SCENE, piece.headless, piece.module);
    if (headless) errors.push(`${piece.what}: the snapshot's ${headless}`);
  }
  const entry = read(HEADLESS_ENTRY);
  if (entry === null) errors.push(`${HEADLESS_ENTRY} does not exist`);
  else if (!namedImports(entry).some(item => item.name === 'headlessSceneFamily' && resolveSource(repo, HEADLESS_ENTRY, item.specifier) === HEADLESS_SCENE)) {
    errors.push(`${HEADLESS_ENTRY} does not route a family's job through headlessSceneFamily (${HEADLESS_SCENE})`);
  }
  for (const rel of HEADLESS_RENDER_PATH) {
    const code = read(rel);
    for (const item of code === null ? [] : namedImports(code)) {
      if (MESH_FLATTENERS.includes(item.name)) errors.push(`${rel} imports ${item.name}: the snapshot draws a family with its shared builder, never a copy flattened for it`);
    }
  }
  const definitions = new Map(builderNames.map(name => [name, []]));
  for (const rel of packageSources(repo)) {
    const code = read(rel);
    for (const name of builderNames) {
      if (new RegExp(`(?:function\\s+${name}\\s*\\(|(?:const|let|var)\\s+${name}\\s*=)`).test(code)) definitions.get(name).push(rel);
    }
  }
  for (const [name, files] of definitions) {
    if (files.length !== 1) errors.push(`${name} is defined ${files.length ? `in ${files.length} places (${files.join(', ')})` : 'nowhere'}; it is ONE shared builder`);
  }
  return { errors, pieceCount: pieces.length };
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  const kit = checkKitBoundaries(repo);
  const slices = checkRendererSlices(repo);
  const host = checkFileViewerBoundary(repo);
  const shared = checkSharedSceneBuilders(repo);
  const errors = [...kit.errors, ...slices.errors, ...host.errors, ...shared.errors];
  if (errors.length) { console.error(errors.join('\n')); process.exitCode = 1; }
  else console.log(`Kit boundaries passed (${kit.sourceCount} format-blind sources); renderer slices passed (${RENDERER_SLICES.join(', ')}: ${slices.sourceCount} sources); the file viewer imports no slice (${host.sourceCount} sources); the viewer and the snapshot CLI share ${shared.pieceCount} scene pieces.`);
}
