#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { isBuiltin } from 'node:module';
import ts from 'typescript';

export function checkDependencies(repo) {
const packages = new Map(['core', 'ui'].map(name => [`@hardcore/${name}`, path.join(repo, 'packages', name)]));
const extensions = ['', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.d.ts', '/index.ts', '/index.tsx', '/index.js'];
function existing(file) {
  const base = file.replace(/\.(?:js|jsx)$/, '');
  return [file, ...extensions.map(ext => base + ext)].find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
}
// Keep filesystem paths native in the graph; classify repository locations
// with one separator so these boundaries also run on Windows.
function repoPath(file) { return path.relative(repo, file).split(path.sep).join('/'); }
function owner(file) { return repoPath(file).split('/').slice(0, 2).join('/'); }
function resolveImport(specifier, file) {
  const clean = specifier.split('?')[0];
  if (clean.startsWith('.')) return existing(path.resolve(path.dirname(file), clean));
  const app = owner(file);
  const aliases = app === 'apps/desktop' ? { '@renderer': 'src/renderer', '@shared': 'src/shared', '@main': 'src/main', '@preload': 'src/preload' } : app === 'apps/web' ? { '@': 'src/client' } : app === 'apps/docs' ? { '@': 'src' } : {};
  for (const [name, target] of Object.entries(aliases)) if (clean.startsWith(name + '/')) return existing(path.join(repo, app, target, clean.slice(name.length + 1)));
  for (const [name, root] of packages) {
    if (clean !== name && !clean.startsWith(name + '/')) continue;
    const exports = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).exports;
    const subpath = clean === name ? '.' : '.' + clean.slice(name.length);
    const key = Object.keys(exports).sort((a, b) => b.length - a.length).find(key => key === subpath || key.includes('*') && subpath.startsWith(key.split('*')[0]) && subpath.endsWith(key.split('*')[1]));
    if (!key) return undefined;
    const value = exports[key];
    let target = typeof value === 'string' ? value : value.import || value.default;
    if (key.includes('*')) target = target.replace('*', subpath.slice(key.split('*')[0].length, key.split('*')[1] ? -key.split('*')[1].length : undefined));
    return existing(path.join(root, target.replace(/^\.\/dist\//, './src/')));
  }
}
function sourceImports(code, file) {
  const ast = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true);
  const imports = [];
  function visit(node) {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      imports.push({ name: node.moduleSpecifier.text, typesOnly: !!(node.isTypeOnly || node.importClause?.isTypeOnly) });
    } else if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || ts.isIdentifier(node.expression) && node.expression.text === 'require') && node.arguments[0] && ts.isStringLiteral(node.arguments[0])) imports.push({ name: node.arguments[0].text, typesOnly: false });
    ts.forEachChild(node, visit);
  }
  visit(ast); return imports;
}
const files = [];
function walk(dir) {
  if (!fs.existsSync(dir)) return;
  for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
    if (['node_modules', 'dist', '_runtime', 'out', '__tests__', 'harness'].includes(item.name)) continue;
    const file = path.join(dir, item.name);
    if (item.isDirectory()) walk(file);
    else if (/\.[cm]?[jt]sx?$/.test(item.name) && !/\.(test|spec)\./.test(item.name)) files.push(file);
  }
}
for (const root of ['apps/docs/src', 'apps/web/src', 'apps/desktop/src', 'packages/core/src', 'packages/ui/src']) walk(path.join(repo, root));
const errors = [];
const edges = new Map();
const nodeModules = new Set();
for (const file of files) {
  const from = owner(file); const code = fs.readFileSync(file, 'utf8'); const imports = sourceImports(code, file);
  if (from === 'packages/ui' && /\b(?:window|globalThis)\.hardcore\b/.test(code)) errors.push(`${path.relative(repo, file)} uses a desktop global`);
  for (const item of imports) {
    if (isBuiltin(item.name)) nodeModules.add(file);
    const resolved = resolveImport(item.name, file);
    const to = resolved && owner(resolved);
    const label = `${path.relative(repo, file)} -> ${item.name}`;
    if (/^(cadgen-js|cad-viewer(?:\/|$)|cadgen-react)/.test(item.name)) errors.push(`${label}: retired package`);
    if (from.startsWith('apps/') && to?.startsWith('apps/') && from !== to) errors.push(`${label}: app-to-app dependency`);
    if (from.startsWith('packages/') && to?.startsWith('apps/')) errors.push(`${label}: package depends on app source`);
    if (from === 'packages/core' && (/^(react(?:-dom)?(?:\/|$)|electron(?:\/|$)|next(?:\/|$)|@hardcore\/ui(?:\/|$))/.test(item.name) || to === 'packages/ui')) errors.push(`${label}: core depends on UI/platform framework`);
    if (from === 'packages/ui' && (isBuiltin(item.name) || /^(electron(?:\/|$)|@renderer\/|@main\/|@shared\/|@\/)/.test(item.name))) errors.push(`${label}: UI depends on a host or Node module`);
    if (from === 'apps/desktop' && repoPath(file).startsWith('apps/desktop/src/renderer/') && to === from && repoPath(resolved).startsWith('apps/desktop/src/main/')) errors.push(`${label}: renderer imports main`);
    if (item.name.startsWith('@hardcore/') && !resolved && !item.name.endsWith('.css')) errors.push(`${label}: missing package export/source`);
    if (item.name.startsWith('.') && !resolved && !/\.(css|svg|png|webp|ico|glb|wasm|json)$/.test(item.name.split('?')[0])) errors.push(`${label}: unresolved relative module`);
    if (resolved && !item.typesOnly) edges.set(file, [...(edges.get(file) || []), resolved]);
  }
}
// FileViewer is usable without importing any concrete renderer or CAD engine.
const start = path.join(repo, 'packages/ui/src/file-viewer/index.ts');
const visited = new Set();
function inspect(file) {
  if (visited.has(file)) return; visited.add(file);
  if (repoPath(file).startsWith('packages/ui/src/renderers/') || repoPath(file).startsWith('packages/core/src/common/')) errors.push(`FileViewer eagerly imports ${path.relative(repo, file)}`);
  for (const dependency of edges.get(file) || []) inspect(dependency);
}
inspect(start);
// Any Node-only helper reachable from UI or an app's browser renderer is a leak,
// even through a re-export or an otherwise framework-independent core module.
for (const root of files.filter(file => ['packages/ui/', 'apps/web/', 'apps/docs/', 'apps/desktop/src/renderer/'].some(prefix => repoPath(file).startsWith(prefix)))) {
  const seen = new Set();
  function checkBrowser(file) {
    if (seen.has(file)) return; seen.add(file);
    if (nodeModules.has(file)) errors.push(`${path.relative(repo, root)} reaches Node-only ${path.relative(repo, file)}`);
    for (const dependency of edges.get(file) || []) checkBrowser(dependency);
  }
  checkBrowser(root);
}
return { errors: [...new Set(errors)], sourceCount: files.length, viewerModuleCount: visited.size };
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
  const result = checkDependencies(repo);
  if (result.errors.length) { console.error(result.errors.join('\n')); process.exitCode = 1; }
  else console.log(`Dependency boundaries passed (${result.sourceCount} source files; ${result.viewerModuleCount} modules in the FileViewer graph).`);
}
