import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { after, test } from 'node:test';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import viteConfig from '../../vite.config.mjs';

const temporary = await mkdtemp(join(tmpdir(), 'web-viewer-links-'));
after(() => rm(temporary, { recursive: true, force: true }));
const { version } = JSON.parse(readFileSync(new URL('../../package.json', import.meta.url), 'utf8'));
let builds = 0;

/** The version this Viewer's app menu shows when Vite builds it with `env`: its config's `define`, through the page's links. */
async function shownVersion(env) {
  const saved = process.env.TEXT_TO_CAD_RELEASE;
  if (env.TEXT_TO_CAD_RELEASE === undefined) delete process.env.TEXT_TO_CAD_RELEASE;
  else process.env.TEXT_TO_CAD_RELEASE = env.TEXT_TO_CAD_RELEASE;
  let config;
  try { config = await viteConfig({ command: 'build', mode: 'production' }); }
  finally { if (saved === undefined) delete process.env.TEXT_TO_CAD_RELEASE; else process.env.TEXT_TO_CAD_RELEASE = saved; }
  const output = join(temporary, `links-${builds += 1}.mjs`);
  await build({
    stdin: { contents: `export {useViewerLinks} from './viewerLinks.js'; export {createElement} from 'react'; export {renderToString} from 'react-dom/server';`,
      resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
    bundle: true, platform: 'node', format: 'esm', outfile: output, define: config.define, logLevel: 'error',
    banner: { js: `import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);` },
  });
  const { useViewerLinks, createElement, renderToString } = await import(pathToFileURL(output).href);
  let links = null;
  renderToString(createElement(() => { links = useViewerLinks(); return null; }));
  return links.version;
}

test('the Viewer shows the version it is: as it is for the release\'s own build, with its checkout\'s commit for any other', async () => {
  const checkout = fileURLToPath(new URL('../..', import.meta.url));
  const commit = execFileSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: checkout, encoding: 'utf8' }).trim();
  assert.equal(await shownVersion({ TEXT_TO_CAD_RELEASE: version }), version);
  assert.match(await shownVersion({}), new RegExp(`^${version.replaceAll('.', '\\.')}-dev\\.${commit}(?:-dirty)?$`, 'u'));
});
