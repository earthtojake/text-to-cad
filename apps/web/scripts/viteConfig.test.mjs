import assert from 'node:assert/strict';
import { test } from 'node:test';

import viteConfig from '../vite.config.mjs';

/** The config Vite builds with, under `env` added to the process's for the call. */
async function configWith(env) {
  const saved = Object.fromEntries(Object.keys(env).map((name) => [name, process.env[name]]));
  Object.assign(process.env, env);
  try {
    return await viteConfig({ command: 'build', mode: 'production' });
  } finally {
    for (const [name, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }
}

test('the dev server lends its engine token to no other origin, and never to the page', async () => {
  const config = await configWith({ CAD_ENGINE_TOKEN: 'dummy-token' });
  assert.equal(config.server.cors, false);
  assert.equal(config.envPrefix, 'VIEWER_');
  assert.ok(!'CAD_ENGINE_TOKEN'.startsWith(config.envPrefix));
  await assert.rejects(configWith({ VIEWER_ENGINE_TOKEN: 'dummy-token' }), /VIEWER_ENGINE_TOKEN: Vite hands every VIEWER_ variable to the page/u);
});
