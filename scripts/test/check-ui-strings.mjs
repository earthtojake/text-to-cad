#!/usr/bin/env node
// Every word the CAD Viewer and the CAD app show reads through the locale files
// (`packages/ui/src/i18n/locales`, English first): a person reading Japanese never meets an
// English label the code spelled itself. This check reads the three source trees that draw them
// (packages/ui/src, apps/web/src, apps/mcp/src; tests and test harnesses aside) and refuses:
//
//   1. JSX text with a word in it;
//   2. a JSX attribute a person reads (`aria-label`, `title`, `placeholder`, `label`, `content`,
//      `tooltip`, …) given an English literal, a template with words, or either as a branch;
//   3. a JSX child that is such a literal (`{open ? "Hide" : "Show"}`);
//   4. an object's `label`, `title`, `message`, `summary`, `recovery`, `hint`, … given an English
//      literal, unless the object says it by its `key` beside it (a constant table: `{ value,
//      label, key }`), or is a progress record (`{ phase, label }`, which `loadingState.js` maps
//      onto its closed vocabulary), or the literal is one of that vocabulary's lines
//      (`kit/status/statusLabels.js`, said by its key on screen);
//   5. a toast given an English literal;
//   6. `t("key")` for a key `en.js` does not have.
//
// What is not language passes on its own: format names, units, brand and product names, keyboard
// chords (`NON_LANGUAGE`). Anything else that must stay as written is one line of
// `UI_STRINGS_ALLOWLIST` — a file, the text, and why — and a line that no longer matches anything
// fails too, so the list never outlives what it excuses. An exception's message is no label: what
// a viewer throws is a diagnostic, said as written, like cadgen's own words.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';

const traverse = traverseModule.default ?? traverseModule;

export const UI_SOURCE_ROOTS = ['packages/ui/src', 'apps/web/src', 'apps/mcp/src'];
export const LOCALE_FILE = 'packages/ui/src/i18n/locales/en.js';
export const STATUS_VOCABULARY_FILE = 'packages/ui/src/renderers/kit/status/statusLabels.js';

// Test renderers: they draw one triangle for the shell's own specs and ship to no person.
const SKIPPED_DIRS = ['packages/ui/src/renderers/harness/', 'packages/ui/src/renderers/shell-harness/'];

const LANGUAGE_ATTRIBUTES = new Set([
  'aria-label', 'aria-description', 'aria-valuetext', 'aria-roledescription', 'aria-placeholder', 'title', 'placeholder',
  'data-placeholder', 'label', 'content', 'alt', 'tooltip', 'hint', 'heading', 'description', 'message', 'summary',
  'caption', 'triggerLabel', 'clipboardLabel', 'clearLabel', 'closeLabel', 'emptyLabel', 'ariaLabel', 'text',
]);
const LANGUAGE_PROPERTIES = new Set([
  'label', 'title', 'tooltip', 'hint', 'description', 'ariaLabel', 'placeholder', 'heading', 'message', 'summary',
  'recovery', 'caption', 'emptyLabel', 'shortLabel', 'text', 'reason', 'busyMessage',
]);
const TOASTS = /^toast(?:\.(?:success|error|warning|info|loading|message))?$/;

// Not language: what reads the same in every locale.
export const NON_LANGUAGE = new Set([
  // Formats and file kinds.
  'STEP', 'STP', 'STL', '3MF', 'GLB', 'glTF', 'DXF', 'XBF', 'SDF', 'URDF', 'SRDF', 'PNG', 'SVG', 'JSON', 'PDF',
  // Brands and products.
  'CAD', 'GitHub', 'Discord', 'text-to-cad', 'cadgen', 'Codex', 'Claude', 'WebGL',
  // Units and symbols.
  'mm', 'mm²', 'mm³', 'kg', 'm', 'rad', 'N', 'N·m', 'm/s', 'rad/s', '°', 'ID',
]);

// A keyboard chord or its prefix ("Ctrl+C", "Shift+"): no language.
const CHORD = /^(?:Ctrl|Shift|Alt|Cmd|Meta|Option)\+\S*$/;

/**
 * Whether `text` has words a person reads: a token, outside `${…}`, with two letters running that
 * is no NON_LANGUAGE token and no key chord ("STEP · mm" has none; "Close ${}" has one).
 */
export function hasWords(text) {
  const tokens = String(text ?? '').replaceAll('${}', ' ').split(/[\s·,:;()]+/).filter(Boolean);
  return tokens.some(token => /[A-Za-z]{2,}/.test(token) && !NON_LANGUAGE.has(token) && !CHORD.test(token));
}

const quasisText = node => node.quasis.map(quasi => quasi.value.cooked ?? quasi.value.raw).join('${}');

/** The literal texts an expression can yield directly: a string, a template, either branch of `?:`, `||`'s right. */
function literalTexts(node) {
  if (!node) return [];
  if (node.type === 'StringLiteral') return [[node, node.value]];
  if (node.type === 'TemplateLiteral') return [[node, quasisText(node)]];
  if (node.type === 'ConditionalExpression') return [...literalTexts(node.consequent), ...literalTexts(node.alternate)];
  if (node.type === 'LogicalExpression' && (node.operator === '||' || node.operator === '??')) return literalTexts(node.right);
  return [];
}

function sourceFiles(dir, repo, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, item.name);
    const rel = path.relative(repo, file).split(path.sep).join('/');
    if (item.isDirectory()) {
      if (item.name === 'node_modules' || item.name === '__fixtures__' || item.name === 'locales') continue;
      if (SKIPPED_DIRS.some(skipped => `${rel}/`.startsWith(skipped))) continue;
      sourceFiles(file, repo, out);
    } else if (/\.(?:[cm]?jsx?|tsx?)$/.test(item.name) && !/\.(?:test|spec)\.|\.d\.ts$/.test(item.name)) out.push(file);
  }
  return out;
}

/** The status vocabulary's English lines: the keys of `KEYS` in `statusLabels.js`. */
function statusVocabulary(repo) {
  const file = path.join(repo, STATUS_VOCABULARY_FILE);
  if (!fs.existsSync(file)) return new Set();
  const ast = parse(fs.readFileSync(file, 'utf8'), { sourceType: 'module', plugins: ['jsx'] });
  const lines = new Set();
  traverse(ast, {
    VariableDeclarator(p) {
      if (p.node.id.name !== 'KEYS') return;
      p.traverse({ ObjectProperty(property) { if (property.node.key.type === 'StringLiteral') lines.add(property.node.key.value); } });
    },
  });
  return lines;
}

async function englishKeys(repo) {
  const file = path.join(repo, LOCALE_FILE);
  if (!fs.existsSync(file)) return null;
  return new Set(Object.keys((await import(pathToFileURL(file).href)).default));
}

/**
 * Every English literal a person would read, as `file:line kind "text"` lines, and every
 * allow-list line that excused nothing.
 * @param {string} repo
 * @param {{ allowlist?: readonly [string, string, string][], roots?: readonly string[] }} [options]
 */
export async function checkUiStrings(repo, { allowlist = UI_STRINGS_ALLOWLIST, roots = UI_SOURCE_ROOTS } = {}) {
  const errors = [];
  const used = new Set();
  const keys = await englishKeys(repo);
  const vocabulary = statusVocabulary(repo);
  for (const root of roots) {
    for (const file of sourceFiles(path.join(repo, root), repo)) {
      const rel = path.relative(repo, file).split(path.sep).join('/');
      const source = fs.readFileSync(file, 'utf8');
      const lines = source.split('\n');
      let ast;
      try {
        ast = parse(source, { sourceType: 'module', plugins: ['jsx', 'typescript'] });
      } catch (error) {
        errors.push(`${rel}: cannot be read (${error.message})`);
        continue;
      }
      const report = (node, kind, text) => {
        if (!hasWords(text)) return;
        const line = node.loc.start.line;
        const shown = text.replace(/\s+/g, ' ').trim();
        const excuse = allowlist.findIndex(([where, what]) => where === rel && (shown.includes(what) || (lines[line - 1] || '').includes(what)));
        if (excuse >= 0) { used.add(excuse); return; }
        errors.push(`${rel}:${line} ${kind} ${JSON.stringify(shown)}`);
      };
      traverse(ast, {
        JSXText(p) { report(p.node, 'JSX text', p.node.value); },
        JSXAttribute(p) {
          const name = p.node.name.type === 'JSXNamespacedName' ? `${p.node.name.namespace.name}:${p.node.name.name.name}` : p.node.name.name;
          if (!LANGUAGE_ATTRIBUTES.has(name) || !p.node.value) return;
          const value = p.node.value.type === 'JSXExpressionContainer' ? p.node.value.expression : p.node.value;
          for (const [node, text] of literalTexts(value)) report(node, `${name}=`, text);
        },
        JSXExpressionContainer(p) {
          if (p.parent.type !== 'JSXElement' && p.parent.type !== 'JSXFragment') return;
          for (const [node, text] of literalTexts(p.node.expression)) report(node, 'JSX child', text);
        },
        ObjectProperty(p) {
          const key = p.node.key.type === 'Identifier' ? p.node.key.name : p.node.key.type === 'StringLiteral' ? p.node.key.value : '';
          if (p.node.computed || !LANGUAGE_PROPERTIES.has(key)) return;
          const said = property => property.type === 'ObjectProperty' && !property.computed
            && ['key', 'phase'].includes(property.key.type === 'Identifier' ? property.key.name : property.key.value);
          if ((p.parent.properties || []).some(said)) return;
          for (const [node, text] of literalTexts(p.node.value)) if (!vocabulary.has(text)) report(node, `${key}:`, text);
        },
        CallExpression(p) {
          const callee = p.node.callee;
          const name = callee.type === 'Identifier' ? callee.name
            : callee.type === 'MemberExpression' && callee.object.type === 'Identifier' && callee.property.type === 'Identifier'
              ? `${callee.object.name}.${callee.property.name}` : '';
          const [first] = p.node.arguments;
          if (TOASTS.test(name)) for (const [node, text] of literalTexts(first)) report(node, `${name}()`, text);
          if (keys && first?.type === 'StringLiteral' && (name === 't' || name === 'english' || name.endsWith('.t'))
            && !keys.has(first.value)) errors.push(`${rel}:${first.loc.start.line} t() names a key en.js does not have: ${JSON.stringify(first.value)}`);
        },
      });
    }
  }
  allowlist.forEach(([where, what], index) => {
    if (!used.has(index)) errors.push(`UI_STRINGS_ALLOWLIST line for ${where} (${JSON.stringify(what)}) matches nothing: delete it`);
  });
  return errors;
}

// What stays as written, one line each: [file, text on the line or the literal, why].
export const UI_STRINGS_ALLOWLIST = [
  ['packages/ui/src/annotation/views.js', 'current view', "a view's name in the prompt the agent reads, not on screen"],
  ['packages/ui/src/renderers/kit/tools/quick-edit/quickEditPrompt.js', 'Snapshot (cad snapshot --annotation)', "a file's label in the prompt the agent reads"],
  ['packages/ui/src/file-viewer/navigation/NavbarLinks.jsx', 'Feedback:', "the title of the GitHub issue Feedback opens, for the project's own tracker"],
  ['packages/ui/src/export/ExportControls.tsx', 'font-normal! leading-4!', "Sonner's class names for a toast's title, no words"],
  ['packages/ui/src/renderers/kit/camera/viewportCameraKit.js', 'Jump to', "each view's English name; `viewPlaneTitle` says it on screen from its sides"],
  ['packages/ui/src/renderers/kit/status/ViewUpdateStatus.jsx', 'Meshing parts', "the status vocabulary's counted meshing line, said by its key (`statusLabels.js`)"],
  ['packages/ui/src/renderers/xbf/xbfMenus.js', 'Viewer', "the empty-space menu descriptor's own name, never drawn"],
  ['apps/mcp/src/host/bridge.ts', 'is not supported', "a JSON-RPC error to the host, not to a person"],
];

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  const errors = await checkUiStrings(repo);
  if (errors.length) {
    console.error(`English the viewer spells itself: say it through a locale key (packages/ui/src/i18n/locales), or allow-list what is no language.\n  ${errors.join('\n  ')}`);
    process.exit(1);
  }
  console.log('Every string the viewer and the CAD app show reads through the locale files.');
}
