// REST at /v1: the same service as MCP, as JSON. Reading a build is public (its id is the
// secret, like the link); everything that runs compute or names you needs a Bearer token.
import { Hono, type Context } from 'hono';
import type { Auth, User } from './auth.ts';
import { CloudError, badRequest, forbidden, notFound, unauthorized } from './errors.ts';
import { isTextPath } from './mime.ts';
import { buildJson, jobJson } from './present.ts';
import type { Build, Service } from './service.ts';
import { encodePath } from './service.ts';
import { asBody, objectKey } from './store.ts';
import { parseWait } from './validate.ts';
import { usageToday } from './limits.ts';

const INLINE_TEXT_BYTES = 1024 * 1024;

export function restRoutes(service: Service, auth: Auth, deps: { usage: (user: User) => ReturnType<typeof usageToday> }) {
  const app = new Hono();
  const { config } = service;
  const maxWait = config.limits.toolWaitSeconds;
  const metadata = `${config.publicUrl}/.well-known/oauth-protected-resource`;

  async function signedIn(c: Context, { allowApiKey = true } = {}): Promise<User> {
    const result = await auth.authenticate(c.req.raw);
    if (!result.ok) {
      const error = unauthorized(result.message);
      error.details = { resource_metadata: metadata };
      error.headers['www-authenticate'] = auth.challenge(metadata, result.reason === 'invalid' ? 'invalid_token' : undefined);
      throw error;
    }
    if (!allowApiKey && result.via === 'api_key') throw forbidden('API keys cannot manage API keys; use the account page or an OAuth token.');
    return result.user;
  }

  async function body(c: Context): Promise<Record<string, unknown>> {
    const text = await c.req.text();
    if (!text.trim()) return {};
    try {
      const value = JSON.parse(text);
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
      return value;
    } catch {
      throw badRequest('the request body must be a JSON object');
    }
  }

  async function buildOr404(id: string): Promise<Build> {
    const build = await service.getBuild(id);
    if (!build) throw notFound(`build ${id} does not exist`);
    return build;
  }

  const fileUrl = (build: Build, path: string) => `${config.publicUrl}/v1/builds/${build.id}/files/${encodePath(path)}`;

  app.post('/builds', async (c) => {
    const user = await signedIn(c);
    const input = await body(c);
    const seconds = parseWait(c.req.query('wait') ?? input.wait, maxWait);
    delete input.wait;
    const { build, deduped } = await service.createBuild(user, input);
    const settled = seconds ? ((await service.waitBuild(build.id, seconds)) ?? build) : build;
    return c.json(buildJson(service, settled, { deduped }), deduped ? 200 : 201);
  });

  app.get('/builds', async (c) => {
    const user = await signedIn(c);
    const limit = Number(c.req.query('limit') ?? 20);
    const builds = await service.listBuilds(user, Number.isFinite(limit) ? limit : 20);
    return c.json({ builds: builds.map((build) => buildJson(service, build)) });
  });

  app.get('/builds/:id', async (c) => {
    const seconds = parseWait(c.req.query('wait'), maxWait);
    const build = (await service.waitBuild(c.req.param('id'), seconds)) ?? null;
    if (!build) throw notFound(`build ${c.req.param('id')} does not exist`);
    return c.json(buildJson(service, build));
  });

  app.get('/builds/:id/files', async (c) => {
    const build = await buildOr404(c.req.param('id'));
    return c.json({
      build: build.id,
      files: service.buildFiles(build).map((file) => ({
        path: file.path,
        kind: file.kind,
        bytes: file.bytes,
        sha256: file.sha256,
        url: fileUrl(build, file.path),
        download: service.objectUrl(objectKey(file.sha256)),
      })),
    });
  });

  app.get('/builds/:id/files/*', async (c) => {
    const build = await buildOr404(c.req.param('id'));
    const prefix = `/v1/builds/${build.id}/files/`;
    const pathname = new URL(c.req.url).pathname;
    let path: string;
    try {
      path = decodeURIComponent(pathname.slice(pathname.indexOf(prefix) + prefix.length));
    } catch {
      throw badRequest('the file path is not valid URL encoding');
    }
    const { file, bytes, type } = await service.readFile(build, path);
    if (isTextPath(file.path) && bytes.byteLength <= INLINE_TEXT_BYTES) {
      return new Response(asBody(bytes), {
        headers: {
          'content-type': type.startsWith('text/') ? type : 'text/plain; charset=utf-8',
          'cache-control': 'public, max-age=31536000, immutable',
          'x-content-type-options': 'nosniff',
          'content-disposition': `inline; filename*=UTF-8''${encodeURIComponent(file.path.split('/').pop()!)}`,
        },
      });
    }
    return c.redirect(service.objectUrl(objectKey(file.sha256)), 302);
  });

  app.post('/builds/:id/snapshot', async (c) => {
    const user = await signedIn(c);
    const input = await body(c);
    const seconds = parseWait(c.req.query('wait') ?? input.wait, maxWait);
    const job = await service.createJob(user, 'snapshot', { ...input, build: c.req.param('id') });
    const settled = seconds ? ((await service.waitJob(job.id, seconds)) ?? job) : job;
    return c.json(jobJson(service, settled), 201);
  });

  app.post('/builds/:id/inspect', async (c) => {
    const user = await signedIn(c);
    const input = await body(c);
    const seconds = parseWait(c.req.query('wait') ?? input.wait, maxWait);
    const job = await service.createJob(user, 'inspect', { ...input, build: c.req.param('id') });
    const settled = seconds ? ((await service.waitJob(job.id, seconds)) ?? job) : job;
    return c.json(jobJson(service, settled), 201);
  });

  app.get('/jobs/:id', async (c) => {
    const user = await signedIn(c);
    const job = await service.requireJobOwner(user, c.req.param('id'));
    const seconds = parseWait(c.req.query('wait'), maxWait);
    const settled = seconds ? ((await service.waitJob(job.id, seconds)) ?? job) : job;
    return c.json(jobJson(service, settled));
  });

  app.get('/me', async (c) => {
    const user = await signedIn(c);
    return c.json({
      user: { id: user.id, email: user.email, name: user.name },
      usage: await deps.usage(user),
      limits: {
        buildTimeoutSeconds: config.limits.buildTimeoutSeconds,
        jobTimeoutSeconds: config.limits.jobTimeoutSeconds,
        vcpus: config.limits.buildVcpus,
        maxFiles: config.limits.maxFiles,
        maxInputBytes: config.limits.maxInputBytes,
        maxOutputBytes: config.limits.maxOutputBytes,
        dailyVcpuSeconds: config.limits.userDailyVcpuSeconds,
      },
      mcp: `${config.publicUrl}/mcp`,
    });
  });

  app.get('/api-keys', async (c) => {
    const user = await signedIn(c);
    return c.json({ keys: await auth.listApiKeys(user) });
  });

  app.post('/api-keys', async (c) => {
    const user = await signedIn(c, { allowApiKey: false });
    const input = await body(c);
    return c.json(await auth.createApiKey(user, typeof input.name === 'string' ? input.name : ''), 201);
  });

  app.delete('/api-keys/:id', async (c) => {
    const user = await signedIn(c);
    if (!(await auth.deleteApiKey(user, c.req.param('id')))) throw notFound(`API key ${c.req.param('id')} does not exist`);
    return c.body(null, 204);
  });

  app.all('*', () => {
    throw new CloudError(404, 'not_found', 'No such API route. See /v1/builds, /v1/jobs/:id, /v1/me, /v1/api-keys.');
  });

  return app;
}
