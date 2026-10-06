import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PNG, PUBLIC_URL, boxSource, fakeSandbox, testServer, type TestServer } from './helpers.ts';

// The compat API is the viewer branch's module; these tests pin how the gateway mounts it.
const calls = vi.hoisted(() => [] as { method: string; path: string; query: string; body?: number; objectUrl: string }[]);
vi.mock('../server/viewerApi.ts', () => ({
  async handleViewerApi(index: { views: string[] }, req: { method: string; path: string; query: URLSearchParams; body?: Uint8Array }, ctx: { objectUrl(sha: string): string; saveSketch(png: Uint8Array, name: string): Promise<string> }) {
    calls.push({ method: req.method, path: req.path, query: req.query.toString(), body: req.body?.byteLength, objectUrl: ctx.objectUrl('a'.repeat(64)) });
    if (req.path === '/__cad/asset') return { status: 302, redirect: ctx.objectUrl('a'.repeat(64)) };
    if (req.path === '/__cad/sketches') return { status: 200, json: { ok: true, path: await ctx.saveSketch(req.body!, 'sketch') } };
    return { status: 200, json: { views: index.views } };
  },
}));

let server: TestServer | undefined;
afterEach(async () => {
  await server?.close();
  server = undefined;
  calls.length = 0;
});

async function builtBox(s: TestServer) {
  const response = await s.request('/v1/builds?wait=5', { method: 'POST', json: { files: { 'src/box.py': boxSource() }, entry: 'src/box.py', title: 'Box <1>' } });
  return response.json();
}

describe('build pages', () => {
  it('redirects a build to its main file and serves the viewer page with OpenGraph tags', async () => {
    server = await testServer();
    await mkdir(path.join(server.dir, 'dist'), { recursive: true });
    await writeFile(path.join(server.dir, 'dist/index.html'), '<!doctype html><html><head><title>CAD</title></head><body><div id="root"></div></body></html>');
    const build = await builtBox(server);

    const redirect = await server.request(`/b/${build.id}`);
    expect(redirect.status).toBe(302);
    expect(redirect.headers.get('location')).toBe(`/b/${build.id}/STEP/box.step`);

    const page = await server.request(`/b/${build.id}/STEP/box.step`);
    expect(page.status).toBe(200);
    const html = await page.text();
    expect(html).toContain('<title>Box &lt;1&gt; · Text-to-CAD</title>');
    expect(html).toContain(`<meta property="og:image" content="${build.thumbnail}">`);
    expect(html).toContain(`<meta property="og:url" content="${PUBLIC_URL}/b/${build.id}/STEP/box.step">`);
    expect(html).toContain('<div id="root"></div>');
  });

  it('says how to build the page when dist/ is missing, and 404s unknown builds', async () => {
    server = await testServer();
    const build = await builtBox(server);
    const missing = await server.request(`/b/${build.id}/STEP/box.step`);
    expect(missing.status).toBe(503);
    expect(await missing.text()).toContain('npm run build -w @text-to-cad/cloud');
    expect((await server.request('/b/AAAAAAAAAAAAAAAA')).status).toBe(404);
  });
});

describe('compat viewer API', () => {
  it('hands /b/<id>/__cad/* to handleViewerApi with the path below the build', async () => {
    server = await testServer();
    const build = await builtBox(server);
    const catalog = await server.request(`/b/${build.id}/__cad/catalog?file=%2FSTEP%2Fbox.step`);
    expect(await catalog.json()).toEqual({ views: ['/STEP/box.step'] });
    expect(calls[0]).toMatchObject({ method: 'GET', path: '/__cad/catalog', query: 'file=%2FSTEP%2Fbox.step', objectUrl: `${PUBLIC_URL}/o/o/${'a'.repeat(64)}` });

    const asset = await server.request(`/b/${build.id}/__cad/asset?file=x`);
    expect(asset.status).toBe(302);
    expect(asset.headers.get('location')).toBe(`${PUBLIC_URL}/o/o/${'a'.repeat(64)}`);

    const tess = await server.request(`/b/${build.id}/__tess_cache/probe`, { method: 'POST', body: '{}' });
    expect(tess.status).toBe(200);
    expect(calls.at(-1)).toMatchObject({ method: 'POST', path: '/__tess_cache/probe', body: 2 });

    const sketch = await (await server.request(`/b/${build.id}/__cad/sketches?name=s`, { method: 'POST', body: PNG })).json();
    expect(sketch.path).toMatch(new RegExp(`^${PUBLIC_URL}/o/sketch/[0-9a-f]{64}\\.png$`));
  });

  it('answers 404 for a build without an export, without calling the API', async () => {
    server = await testServer({ sandbox: fakeSandbox(() => ({ result: { outputs: [] } })) });
    const build = await builtBox(server);
    const response = await server.request(`/b/${build.id}/__cad/server`);
    expect(response.status).toBe(404);
    expect(calls).toHaveLength(0);
  });
});
