import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { NOTICE_FILE, bundledPackages, packageDirOf, thirdPartyLicenses } from './third-party-licenses.mjs';

function tree(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'tpl-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const write = (relative, text) => {
    fs.mkdirSync(path.dirname(path.join(root, relative)), { recursive: true });
    fs.writeFileSync(path.join(root, relative), text);
  };
  write('node_modules/plain/package.json', JSON.stringify({ name: 'plain', version: '1.0.0', license: 'MIT' }));
  write('node_modules/plain/LICENSE', 'MIT text\n');
  write('node_modules/plain/lib/a.js', '');
  write('node_modules/plain/lib/b.js', '');
  write('node_modules/@scope/pkg/package.json', JSON.stringify({ name: '@scope/pkg', version: '2.0.0', license: { type: 'BSD-3-Clause' } }));
  write('node_modules/@scope/pkg/LICENCE.md', 'BSD text');
  write('node_modules/@scope/pkg/index.js', '');
  write('node_modules/bare/package.json', JSON.stringify({ name: 'bare', version: '3.0.0', license: 'ISC', author: 'A. Author', repository: { url: 'https://example.test/bare' } }));
  write('node_modules/bare/index.js', '');
  write('node_modules/none/package.json', JSON.stringify({ name: 'none', version: '4.0.0' }));
  write('node_modules/none/LICENSE', 'text');
  write('node_modules/none/index.js', '');
  write('packages/own/src/x.js', '');
  return root;
}

test('a bundled module is named by its package folder, and this repository\'s own and virtual ones by none', () => {
  assert.equal(packageDirOf('/r/node_modules/three/build/three.module.js?v=1'), '/r/node_modules/three');
  assert.equal(packageDirOf('/r/node_modules/a/node_modules/@s/b/x.js'), '/r/node_modules/a/node_modules/@s/b');
  assert.equal(packageDirOf('/r/packages/core/dist/index.js'), null);
  assert.equal(packageDirOf('\0vite/preload-helper'), null);
});

test('each bundled package once, with its declared licence and the text it ships, or where its text is kept', (t) => {
  const root = tree(t);
  const found = bundledPackages([
    `${root}/node_modules/plain/lib/a.js`, `${root}/node_modules/plain/lib/b.js`,
    `${root}/node_modules/@scope/pkg/index.js`, `${root}/node_modules/bare/index.js`, `${root}/packages/own/src/x.js`,
  ]);
  assert.deepEqual(found.map(entry => [entry.name, entry.version, entry.license]),
    [['@scope/pkg', '2.0.0', 'BSD-3-Clause'], ['bare', '3.0.0', 'ISC'], ['plain', '1.0.0', 'MIT']]);
  assert.equal(found[2].text, 'MIT text');
  assert.match(found[1].text, /ships no licence text; its package\.json declares ISC\.\nAuthor: A\. Author\nRepository: https:\/\/example\.test\/bare/);
  assert.throws(() => bundledPackages([`${root}/node_modules/none/index.js`]), /declare no licence: none@4\.0\.0/);
});

test('the build writes the notice of what its chunks and its workers\' chunks hold, beside the page', (t) => {
  const root = tree(t);
  const out = path.join(root, 'dist');
  fs.mkdirSync(out);
  const licenses = thirdPartyLicenses();
  const [worker] = licenses.worker();
  const page = licenses.plugin();
  worker.generateBundle.handler({}, { 'w.js': { type: 'chunk', moduleIds: [`${root}/node_modules/@scope/pkg/index.js`] } });
  page.generateBundle.handler({}, {
    'a.js': { type: 'chunk', moduleIds: [`${root}/node_modules/plain/lib/a.js`, `${root}/packages/own/src/x.js`] },
    'a.css': { type: 'asset' },
  });
  page.writeBundle({ dir: out });
  const notice = fs.readFileSync(path.join(out, NOTICE_FILE), 'utf8');
  assert.match(notice, /^  @scope\/pkg 2\.0\.0 \(BSD-3-Clause\)\n  plain 1\.0\.0 \(MIT\)\n/m);
  assert.match(notice, /BSD text/);
  assert.match(notice, /MIT text/);
  assert.doesNotMatch(notice, /bare|own/);
});
