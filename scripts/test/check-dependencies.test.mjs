import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { checkDependencies } from './check-dependencies.mjs';
function fixture(files, run) {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'hardcore-boundaries-'));
  const base={
    'packages/core/package.json': JSON.stringify({exports:{'./lib/*':'./dist/lib/*'}}),
    'packages/ui/package.json': JSON.stringify({exports:{'./file-viewer':{import:'./dist/file-viewer/index.js'}}}),
    'packages/ui/src/file-viewer/index.ts':'export const FileViewer = 1;',
  };
  for(const [name,code] of Object.entries({...base,...files})) { const file=path.join(root,name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,code); }
  try { run(checkDependencies(root)); } finally { fs.rmSync(root,{recursive:true,force:true}); }
}
test('accepts an app consuming compiled public UI exports',()=>fixture({'apps/web/src/App.tsx':"import { FileViewer } from '@hardcore/ui/file-viewer';"},result=>assert.deepEqual(result.errors,[])));
test('resolves aliases and extensionless transitive reexports',()=>fixture({
  'apps/desktop/src/renderer/main.ts':"import '@renderer/bridge';",
  'apps/desktop/src/renderer/bridge.ts':"export * from '../../../web/src/private';",
  'apps/web/src/private.ts':'export const secret = 1;',
},result=>assert.ok(result.errors.some(error=>error.includes('app-to-app')))));
test('rejects app imports from packages and undeclared exports',()=>fixture({
  'packages/ui/src/file-viewer/index.ts':"export * from '../../../../apps/web/src/private'; import '@hardcore/core/private';",
  'apps/web/src/private.ts':'export const value = 1;',
},result=>{assert.ok(result.errors.some(error=>error.includes('depends on app')));assert.ok(result.errors.some(error=>error.includes('missing package export')));}));
test('rejects Node builtins reached through a dynamic core import',()=>fixture({
  'apps/web/src/App.ts':"const read = () => import('@hardcore/core/lib/node.js');",
  'packages/core/src/lib/node.js':"import fs from 'fs'; export const read = fs.readFileSync;",
},result=>assert.ok(result.errors.some(error=>error.includes('reaches Node-only')))));
test('keeps concrete renderers out of the FileViewer import graph',()=>fixture({
  'packages/ui/src/file-viewer/index.ts':"export * from '../renderers/cad';",
  'packages/ui/src/renderers/cad/index.ts':'export const cad = 1;',
},result=>assert.ok(result.errors.some(error=>error.includes('eagerly imports')))));
test('rejects desktop renderer imports of main-process modules',()=>fixture({
  'apps/desktop/src/renderer/view.ts':"import '../main/private';",
  'apps/desktop/src/main/private.ts':'export const secret = 1;',
},result=>assert.ok(result.errors.some(error=>error.includes('renderer imports main')))));
