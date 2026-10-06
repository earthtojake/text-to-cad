// A build's pages. /b/<id> redirects to its main file; /b/<id>/<path> is the viewer page
// (the SPA's index.html with OpenGraph tags for the build). /b/<id>/__cad/* and
// /b/<id>/__tess_cache/* are the read-only copy of the viewer API recorded in the build's
// export (law 3: viewing never wakes compute).
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { Hono, type Context } from 'hono';
import { CloudError } from './errors.ts';
import { isBuildId } from './ids.ts';
import { buildTitle } from './present.ts';
import type { Build, Service } from './service.ts';
import { encodePath } from './service.ts';
import { asBody, objectKey } from './store.ts';
import { handleViewerApi, type ViewerApiResponse } from './viewerApi.ts';
import { escapeHtml, htmlResponse, page } from './web.ts';

const MAX_VIEWER_BODY = 21 * 1024 * 1024;

export function toResponse(result: ViewerApiResponse, head: boolean): Response {
  const headers = new Headers(result.headers ?? {});
  if (result.redirect) {
    headers.set('location', result.redirect);
    return new Response(null, { status: result.status >= 300 && result.status < 400 ? result.status : 302, headers });
  }
  if (result.json !== undefined) {
    if (!headers.has('content-type')) headers.set('content-type', 'application/json');
    return new Response(head ? null : JSON.stringify(result.json), { status: result.status, headers });
  }
  return new Response(head || !result.body ? null : asBody(result.body), { status: result.status, headers });
}

export function ogTags(service: Service, build: Build, url: string): string[] {
  const title = `${buildTitle(build)} · Text-to-CAD`;
  const description = build.status === 'succeeded'
    ? `CAD model ${build.primary ?? ''}, built from code and opened in the CAD viewer.`.replace('  ', ' ')
    : `CAD build ${build.id} (${build.status}).`;
  const tags = [
    ['og:type', 'website'],
    ['og:title', title],
    ['og:description', description],
    ['og:url', url],
    ['og:site_name', 'Text-to-CAD'],
  ].map(([property, content]) => `<meta property="${property}" content="${escapeHtml(content)}">`);
  tags.push(`<meta name="description" content="${escapeHtml(description)}">`);
  tags.push('<meta name="robots" content="noindex">');
  if (build.thumbnailKey) {
    const image = service.objectUrl(build.thumbnailKey);
    tags.push(
      `<meta property="og:image" content="${escapeHtml(image)}">`,
      '<meta property="og:image:width" content="1200">',
      '<meta property="og:image:height" content="630">',
      '<meta name="twitter:card" content="summary_large_image">',
      `<meta name="twitter:image" content="${escapeHtml(image)}">`,
    );
  } else {
    tags.push('<meta name="twitter:card" content="summary">');
  }
  return tags;
}

export function injectHead(html: string, title: string, tags: string[]): string {
  const titled = /<title>[\s\S]*?<\/title>/i.test(html)
    ? html.replace(/<title>[\s\S]*?<\/title>/i, `<title>${escapeHtml(title)}</title>`)
    : html.replace(/<head([^>]*)>/i, `<head$1><title>${escapeHtml(title)}</title>`);
  return titled.replace(/<\/head>/i, `${tags.join('\n')}\n</head>`);
}

export function pageRoutes(service: Service) {
  const app = new Hono();
  const indexFile = path.join(service.config.distDir, 'index.html');
  let cached: { mtimeMs: number; html: string } | null = null;

  async function indexHtml(): Promise<string | null> {
    try {
      const info = await stat(indexFile);
      if (!cached || cached.mtimeMs !== info.mtimeMs) cached = { mtimeMs: info.mtimeMs, html: await readFile(indexFile, 'utf8') };
      return cached.html;
    } catch {
      return null;
    }
  }

  async function compat(c: Context) {
    const id = c.req.param('build')!;
    if (!isBuildId(id)) return c.json({ error: 'No such build.' }, 404);
    const index = await service.exportIndex(id);
    if (!index) {
      const build = await service.getBuild(id);
      return c.json({ error: build ? `Build ${id} has no viewer export (${build.exportError ?? build.status}).` : `No such build: ${id}.` }, 404);
    }
    const url = new URL(c.req.url);
    const method = c.req.method.toUpperCase();
    let body: Uint8Array | undefined;
    if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
      if (Number(c.req.header('content-length') ?? 0) > MAX_VIEWER_BODY) throw new CloudError(413, 'too_large', 'The request body is too large.');
      body = new Uint8Array(await c.req.arrayBuffer());
      if (body.byteLength > MAX_VIEWER_BODY) throw new CloudError(413, 'too_large', 'The request body is too large.');
    }
    const result = await handleViewerApi(index, { method, path: url.pathname.slice(`/b/${id}`.length), query: url.searchParams, body }, {
      objectUrl: (sha256) => service.objectUrl(objectKey(sha256)),
      saveSketch: (png) => service.saveSketch(png),
    });
    return toResponse(result, method === 'HEAD');
  }

  app.all('/b/:build/__cad/*', compat);
  app.all('/b/:build/__tess_cache/*', compat);

  async function viewerPage(c: Context, build: Build) {
    const html = await indexHtml();
    if (html === null) {
      return htmlResponse(c, page('Viewer not built', `<h1>The viewer page is not built</h1>
<p>This server has no <code>dist/index.html</code>. Build it with:</p>
<p class="key">npm run build -w @text-to-cad/cloud</p>`), 503);
    }
    const url = new URL(c.req.url);
    const canonical = `${service.config.publicUrl}${url.pathname}`;
    c.header('x-content-type-options', 'nosniff');
    c.header('referrer-policy', 'strict-origin-when-cross-origin');
    c.header('x-robots-tag', 'noindex');
    c.header('cache-control', 'no-cache');
    return c.html(injectHead(html, `${buildTitle(build)} · Text-to-CAD`, ogTags(service, build, canonical)));
  }

  async function findBuild(c: Context): Promise<Build | Response> {
    const id = c.req.param('id')!;
    const build = isBuildId(id) ? await service.getBuild(id) : null;
    if (!build) return htmlResponse(c, page('Not found', `<h1>No such build</h1><p>There is no build <code>${escapeHtml(id)}</code>.</p>`), 404);
    return build;
  }

  app.get('/b/:id', async (c) => {
    const build = await findBuild(c);
    if (build instanceof Response) return build;
    if (build.primary) return c.redirect(`/b/${build.id}/${encodePath(build.primary)}`, 302);
    return viewerPage(c, build);
  });

  app.get('/b/:id/*', async (c) => {
    const build = await findBuild(c);
    if (build instanceof Response) return build;
    return viewerPage(c, build);
  });

  return app;
}
