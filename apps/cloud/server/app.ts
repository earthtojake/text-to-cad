// The cloud server as one Hono app. Every dependency is injected, so tests run the real
// routes over an in-memory database, a temporary store and a fake sandbox.
import { Hono } from 'hono';
import { bodyLimit } from 'hono/body-limit';
import { errorBody, isCloudError } from './errors.ts';
import { usageToday } from './limits.ts';
import { handleMcp } from './mcp.ts';
import { pageRoutes } from './pages.ts';
import { restRoutes } from './rest.ts';
import { createService, type Deps, type Service } from './service.ts';
import { serveDist, serveFsObject } from './static.ts';
import { webRoutes } from './web.ts';

export type { Deps } from './service.ts';

export interface AppOptions {
  /** Serve dist/ assets and the fs store's /o/* objects (the node entry; Vercel serves its own). */
  serveFiles?: boolean;
}

export function buildApp(deps: Deps, options: AppOptions = {}): { app: Hono; service: Service } {
  const service = createService(deps);
  const { config, auth } = deps;
  const usage = (user: { id: string }) => usageToday(deps.db, config.limits, deps.clock, user.id);
  const app = new Hono();

  app.onError((error, c) => {
    if (isCloudError(error)) {
      for (const [name, value] of Object.entries(error.headers)) c.header(name, value);
      return c.json(errorBody(error), error.status as 400);
    }
    (deps.log ?? ((message: string, extra?: unknown) => console.error(`[cloud] ${message}`, extra)))('unhandled error', {
      path: new URL(c.req.url).pathname,
      error: String((error as Error)?.stack ?? error),
    });
    return c.json({ error: { code: 'internal', message: 'Something went wrong on the server.' } }, 500);
  });

  // Bodies are capped before anything reads them: a build's files (20 MB, plus base64),
  // a sketch (20 MiB), and small forms.
  const limit = (maxSize: number) => bodyLimit({
    maxSize,
    onError: (c) => c.json({ error: { code: 'too_large', message: `The request body is larger than ${maxSize} bytes.` } }, 413),
  });
  app.use('/mcp', limit(32 * 1024 * 1024));
  app.use('/v1/*', limit(32 * 1024 * 1024));
  app.use('/b/*', limit(21 * 1024 * 1024));
  app.use('/account/*', limit(64 * 1024));
  app.use('/auth/*', limit(64 * 1024));

  if (options.serveFiles && deps.store.kind === 'fs') {
    const store = deps.store;
    app.on(['GET', 'HEAD'], '/o/*', (c) => serveFsObject(c, store));
  }

  app.get('/healthz', (c) => c.json({ ok: true, cadgen: config.cadgenVersion, sandbox: deps.sandbox.kind }));

  app.get('/.well-known/oauth-protected-resource', (c) => c.json(auth.protectedResourceMetadata(config.publicUrl)));
  app.get('/.well-known/oauth-protected-resource/mcp', (c) => c.json(auth.protectedResourceMetadata(`${config.publicUrl}/mcp`)));

  app.all('/mcp', (c) => handleMcp(c.req.raw, service, auth));

  app.route('/v1', restRoutes(service, auth, { usage }));

  // Vercel Cron calls GET with `Authorization: Bearer $CRON_SECRET`.
  app.on(['GET', 'POST'], '/internal/sweep', async (c) => {
    const expected = config.cronSecret ? `Bearer ${config.cronSecret}` : null;
    if (!expected || c.req.header('authorization') !== expected) return c.json({ error: { code: 'forbidden', message: 'forbidden' } }, 403);
    return c.json(await service.sweep());
  });

  app.route('/', webRoutes(service, auth, { usage }));
  app.route('/', pageRoutes(service));

  app.notFound(async (c) => {
    if (options.serveFiles && (c.req.method === 'GET' || c.req.method === 'HEAD')) {
      const file = await serveDist(c, config.distDir);
      if (file) return file;
    }
    return c.json({ error: { code: 'not_found', message: 'Not found.' } }, 404);
  });

  return { app, service };
}

export function createApp(deps: Deps, options: AppOptions = {}): Hono {
  return buildApp(deps, options).app;
}
