// Local entry: `npm run dev -w @text-to-cad/cloud` (or scripts/cloud/dev.sh). Serves the app,
// the built viewer page's assets from dist/, and the fs store's objects at /o/*.
import { serve } from '@hono/node-server';
import { buildApp } from './app.ts';
import { depsFromEnv } from './deps.ts';

const deps = await depsFromEnv(process.env);
const { app, service } = buildApp(deps, { serveFiles: true });
// A PGlite database belongs to this one process: whatever it shows running was running in
// a process that has exited, and would hold its owner's one-build slot until swept.
if (deps.db.kind === 'pglite') {
  const swept = await service.sweep({ all: true });
  if (swept.builds || swept.jobs) console.log(`[cloud] failed ${swept.builds} build(s) and ${swept.jobs} job(s) left running by an earlier server`);
}

const sweeper = setInterval(() => {
  service.sweep().catch((error) => console.error('[cloud] sweep failed', error));
}, 60_000);
sweeper.unref();

const server = serve({ fetch: app.fetch, port: deps.config.port, hostname: deps.config.host }, (info) => {
  console.log(`[cloud] listening on http://${info.address}:${info.port} (public URL ${deps.config.publicUrl}; auth ${deps.config.auth.mode}; sandbox ${deps.sandbox.kind}; storage ${deps.store.kind}; db ${deps.db.kind})`);
});

async function shutdown() {
  clearInterval(sweeper);
  server.close();
  await service.idle();
  await deps.db.close();
  process.exit(0);
}
process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);
