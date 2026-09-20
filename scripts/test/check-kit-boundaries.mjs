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
  ['camera/ViewPlaneControl.js', 'view selector', 'user-visible aria label of the same control ("2D view selector" / "Perspective selector")'],
  ['viewport/useViewerRuntime.js', 'displayRecords: []', 'runtime slot the current scene builders fill; it leaves with the STEP scene (renderer-split phase 5)'],
  ['viewport/renderDepthPolicy.js', 'displayRecords: runtime?.displayRecords', 'passes that same slot to the depth fit; leaves with it'],
  ['status/loadingState.js', 'building robot', "a loader's own progress label, matched as text to bucket it under \"Preparing view\"; it leaves when that loader reports a stage instead (renderer-split phase 3)"],
  ['view-settings/viewerDisplaySettings.js', 'buildStepClipPatch', "core's clip-settings API carries STEP in its names; the settings model only passes the Clip section through"],
  ['view-settings/DisplaySettingsTab.js', 'DEFAULT_STEP_CLIP_SETTINGS', 'same core API, read by the opt-in Clip section'],
  ['view-settings/DisplaySettingsTab.js', 'normalizeStepClipSettings', 'same core API, read by the opt-in Clip section'],
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
// lazy-loaded and deleted alone. A slice joins this list when it is split out of
// the legacy `cad` renderer; `workspace` is held to the same rule.
export const RENDERERS_ROOT = 'packages/ui/src/renderers';
export const RENDERER_SLICES = ['glb', 'mesh', 'robot', 'workspace'];
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

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  const kit = checkKitBoundaries(repo);
  const slices = checkRendererSlices(repo);
  const errors = [...kit.errors, ...slices.errors];
  if (errors.length) { console.error(errors.join('\n')); process.exitCode = 1; }
  else console.log(`Kit boundaries passed (${kit.sourceCount} format-blind sources); renderer slices passed (${RENDERER_SLICES.join(', ')}: ${slices.sourceCount} sources).`);
}
