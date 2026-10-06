import { describe, expect, it } from 'vitest';
import { listFolder, normalizeVirtualPath, parseExportIndex, recordedObject, searchFolder, type ExportIndex } from './exportIndex.ts';
import { emptyTessBatch, handleViewerApi, viewerApiPath, type ViewerApiContext } from './viewerApi.ts';

const sha = (seed: string) => seed.padEnd(64, '0');
const TREE = sha('ab');
const SURF = sha('cd');
const row = (file: string, extra: Record<string, unknown> = {}) => ({ schemaVersion: 4, entries: [{ file, kind: 'part', url: `/__cad/asset?file=${encodeURIComponent(file)}&v=1`, hash: 'h', bytes: 1, ...extra }], revision: 'r' });

/** A small synthetic export: a STEP part, a DXF, an STL under a folder, a robot and its mesh, a source file. */
function synthetic(): ExportIndex {
  return parseExportIndex({
    schema: 1, cadgen: '0.7.14',
    files: [
      { path: '/DXF/plate.dxf', kind: 'dxf', bytes: 10, sha256: sha('1') },
      { path: '/STEP/bracket.step', kind: 'step', bytes: 10, sha256: sha('2') },
      { path: '/meshes/arm/tetra.stl', kind: 'stl', bytes: 10, sha256: sha('3') },
      { path: '/robot.urdf', kind: 'urdf', bytes: 10, sha256: sha('4') },
      { path: '/src/bracket.py', kind: 'other', bytes: 10, sha256: sha('5') },
      { path: '/src/notes.txt', kind: 'other', bytes: 10, sha256: sha('6') },
    ],
    views: ['/STEP/bracket.step', '/DXF/plate.dxf', '/meshes/arm/tetra.stl', '/robot.urdf'],
    routes: {
      '/__cad/server': { '': { app: 'cad-viewer', start: '/', pick: false } },
      '/__cad/catalog': { '': { schemaVersion: 4, entries: [], revision: 'empty' }, '/STEP/bracket.step': row('/STEP/bracket.step', { url: `/__cad/store?file=${TREE}&documentHash=d1`, hash: TREE }), '/DXF/plate.dxf': row('/DXF/plate.dxf') },
      '/__cad/artifact': { '/STEP/bracket.step': { state: 'compiled' }, '/DXF/plate.dxf': { state: 'compiled' } },
      '/__cad/preview': { '/STEP/bracket.step': { output: '/STEP/bracket.step', file: '/STEP/bracket.step', state: 'disconnected', revision: null } },
      '/__cad/drawing': { '/DXF/plate.dxf': { schemaVersion: 1, primitives: [] } },
      '/__cad/asset': { '/STEP/bracket.step': { object: sha('2'), type: 'application/step', bytes: 10 }, '/DXF/plate.dxf': { object: sha('1'), type: 'application/dxf', bytes: 10 } },
      '/__cad/store': { [`/${TREE}/assembly.json`]: { object: sha('ee'), type: 'application/json', bytes: 20 }, [`/${TREE}/components/c1.surf`]: { object: SURF, type: 'application/octet-stream', bytes: 30 }, [SURF]: { object: SURF, type: 'application/octet-stream', bytes: 30 } },
    },
  });
}

const ctx: ViewerApiContext = {
  objectUrl: digest => `https://objects.example/o/${digest}`,
  saveSketch: async (png, name) => `https://objects.example/sketch/${name}-${png.byteLength}.png`,
};
const index = synthetic();
const get = (path: string, query: Record<string, string> = {}, method = 'GET') => handleViewerApi(index, { method, path, query: new URLSearchParams(query) }, ctx);
const post = (path: string, body?: Uint8Array | string, query: Record<string, string> = {}, headers: Record<string, string> | undefined = { 'x-cadgen-viewer': '1' }) =>
  handleViewerApi(index, { method: 'POST', path, query: new URLSearchParams(query), body: typeof body === 'string' ? new TextEncoder().encode(body) : body, headers }, ctx);

describe('the export index', () => {
  it('refuses a malformed export and normalizes virtual paths', () => {
    expect(() => parseExportIndex({ schema: 2 })).toThrow(/schema/);
    expect(() => parseExportIndex({ ...synthetic(), views: [] })).toThrow(/views/);
    expect(() => parseExportIndex({ ...synthetic(), routes: { ...synthetic().routes, '/__cad/asset': { a: { object: 'short', type: 't', bytes: 1 } } } })).toThrow(/asset/);
    expect(normalizeVirtualPath('STEP//a.step/')).toBe('/STEP/a.step');
    expect(normalizeVirtualPath('')).toBe('/');
    expect(recordedObject(index, '/__cad/store', `${TREE}/components/c1.surf`)?.object).toBe(SURF);
  });
  it('lists folders and searches as the viewer does: subfolders first, CAD files only, natural order', () => {
    expect(listFolder(index, '/')).toEqual({ path: '/', entries: [{ name: 'DXF', kind: 'directory' }, { name: 'meshes', kind: 'directory' }, { name: 'src', kind: 'directory' }, { name: 'STEP', kind: 'directory' }, { name: 'robot.urdf', kind: 'file' }], truncated: false });
    expect(listFolder(index, '/src')).toEqual({ path: '/src', entries: [], truncated: false });
    expect(listFolder(index, '/meshes/')).toEqual({ path: '/meshes', entries: [{ name: 'arm', kind: 'directory' }], truncated: false });
    expect(listFolder(index, '/nowhere')).toBeNull();
    expect(searchFolder(index, '/', 'T')).toEqual({ path: '/', results: ['/robot.urdf', '/DXF/plate.dxf', '/STEP/bracket.step', '/meshes/arm/tetra.stl'], truncated: false });
    expect(searchFolder(index, '/meshes', 'tetra')).toEqual({ path: '/meshes', results: ['/meshes/arm/tetra.stl'], truncated: false });
  });
});

describe('the compat viewer API', () => {
  it('answers recorded JSON exactly, with or without the mount prefix', async () => {
    expect(viewerApiPath('/b/k7Qx2/__cad/catalog')).toBe('/__cad/catalog');
    expect(viewerApiPath('/__tess_cache/probe')).toBe('/__tess_cache/probe');
    const server = await get('/b/k7Qx2/__cad/server');
    expect(server).toMatchObject({ status: 200, json: { app: 'cad-viewer', start: '/' }, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });
    expect((await get('/__cad/catalog', { file: '/STEP/bracket.step' })).json).toEqual(index.routes['/__cad/catalog']['/STEP/bracket.step']);
    expect((await get('/__cad/artifact', { file: '/STEP/bracket.step' })).json).toEqual({ state: 'compiled' });
    expect((await get('/__cad/preview', { file: '/STEP/bracket.step' })).json).toMatchObject({ state: 'disconnected' });
    expect((await get('/__cad/drawing', { file: '/DXF/plate.dxf' })).json).toEqual({ schemaVersion: 1, primitives: [] });
  });
  it('answers a file the export lacks as the viewer answers a missing file', async () => {
    expect((await get('/__cad/catalog')).json).toEqual({ schemaVersion: 4, entries: [], revision: 'empty' });
    expect((await get('/__cad/catalog', { file: '/STEP/missing.step' })).json).toEqual({ schemaVersion: 4, entries: [], revision: 'empty' });
    expect((await get('/__cad/artifact', { file: '/STEP/missing.step' })).json).toEqual({ state: 'failed', error: 'Artifact source not found: /STEP/missing.step' });
    expect((await get('/__cad/artifact', { file: '/meshes/arm/tetra.stl' })).json).toEqual({ state: 'compiled' });
    expect(await get('/__cad/artifact')).toMatchObject({ status: 400, json: { error: 'name the file by its absolute path' } });
    expect((await get('/__cad/preview', { file: '/STEP/missing.step' })).json).toEqual({ output: '/STEP/missing.step', file: '/STEP/missing.step', state: 'disconnected', revision: null });
    expect(await get('/__cad/preview', { file: '/DXF/plate.dxf' })).toMatchObject({ status: 400, json: { error: 'A build status requires a STEP output path' } });
    expect(await get('/__cad/drawing', { file: '/DXF/missing.dxf' })).toMatchObject({ status: 404, json: { error: 'Not found' } });
    expect(await get('/__cad/drawing', { file: '/STEP/bracket.step' })).toMatchObject({ status: 400, json: { error: '/__cad/drawing renders DXF drawings; bracket.step is not a .dxf file' } });
    expect(await get('/__cad/drawing')).toMatchObject({ status: 400 });
    expect(await get('/__cad/asset', { file: '/src/bracket.py' })).toMatchObject({ status: 404, json: { error: 'Not found' } });
    expect(await get('/__cad/nothing')).toMatchObject({ status: 404, json: { error: 'Not found' } });
    expect(await get('/elsewhere')).toMatchObject({ status: 404 });
  });
  it('sends bytes to the object store: assets and store files, by file or object, GET and HEAD alike', async () => {
    const asset = await get('/__cad/asset', { file: '/STEP/bracket.step', v: '1' });
    expect(asset).toMatchObject({ status: 302, redirect: `https://objects.example/o/${sha('2')}`, headers: { location: `https://objects.example/o/${sha('2')}`, 'cache-control': 'public, max-age=31536000, immutable' } });
    expect(await get('/__cad/store', { file: `/${TREE}/assembly.json`, documentHash: 'd1' })).toMatchObject({ status: 302, redirect: `https://objects.example/o/${sha('ee')}` });
    expect(await get('/__cad/store', { file: `${TREE}/components/c1.surf`, documentHash: 'd1' })).toMatchObject({ status: 302, redirect: `https://objects.example/o/${SURF}` });
    expect(await get('/__cad/store', { tree: TREE, surfaceInput: sha('11'), object: SURF })).toMatchObject({ status: 302, redirect: `https://objects.example/o/${SURF}` });
    expect(await get('/__cad/store', { file: `/${TREE}/components/other.surf` })).toMatchObject({ status: 404, json: { error: 'Not found' } });
    const head = await get('/__cad/store', { file: `/${TREE}/components/c1.surf` }, 'HEAD');
    expect(head).toMatchObject({ status: 302, redirect: `https://objects.example/o/${SURF}` });
    expect(head.json).toBeUndefined();
    expect((await get('/__cad/catalog', {}, 'HEAD')).json).toBeUndefined();
  });
  it('computes the explorer and answers the shared routes as a hosted build has them', async () => {
    expect((await get('/__cad/folder', { path: '/STEP' })).json).toEqual({ path: '/STEP', entries: [{ name: 'bracket.step', kind: 'file' }], truncated: false });
    expect(await get('/__cad/folder', { path: '/nowhere' })).toMatchObject({ status: 404, json: { error: 'No folder at /nowhere' } });
    expect(await get('/__cad/folder', { path: 'STEP' })).toMatchObject({ status: 400 });
    expect((await get('/__cad/search', { path: '/', q: 'plate' })).json).toEqual({ path: '/', results: ['/DXF/plate.dxf'], truncated: false });
    expect((await get('/__cad/recents')).json).toEqual({ recents: [] });
    expect(await get('/__cad/thumbnail', { name: 'x' })).toMatchObject({ status: 404 });
    expect((await get('/__cad/version')).json).toEqual({ notice: null });
    expect((await get('/__cad/analytics')).json).toEqual({ ask: false, sharing: false, reason: 'unavailable', policy: '' });
    expect((await get('/__cad/features')).json).toEqual({ quickEdit: true });
    expect((await post('/__cad/features', '{"quickEdit":false}')).json).toEqual({ quickEdit: false });
    expect(await post('/__cad/features', '{"quickEdit":"no"}')).toMatchObject({ status: 400 });
  });
  it('keeps the tessellation cache empty and accepts nothing', async () => {
    expect(await get(`/__tess_cache/${sha('aa')}-t4-p4.tess`, { object: SURF, maxBytes: '100' })).toEqual({ status: 404, headers: { 'content-length': '0' } });
    expect(await get(`/__tess_cache/${sha('aa')}-t4-p4.tess`, { object: 'nope', maxBytes: '100' })).toEqual({ status: 400, headers: { 'content-length': '0' } });
    expect(await get('/__tess_cache/../etc.tess', { object: SURF, maxBytes: '1' })).toMatchObject({ status: 403 });
    expect((await post('/__tess_cache/probe', JSON.stringify({ tessellationInputs: ['a', 'b'] }))).json).toEqual({ entries: {} });
    expect(await post('/__tess_cache/probe', '{"entries":[]}')).toMatchObject({ status: 400, json: { error: 'bad tessellation probe request' } });
    const batch = await post('/__tess_cache/batch', JSON.stringify({ entries: [{ tessellationInput: 'a', object: SURF, maxBytes: 1 }, { tessellationInput: 'b', object: SURF, maxBytes: 1 }] }));
    expect(batch).toMatchObject({ status: 200, headers: { 'content-type': 'application/octet-stream' } });
    expect(batch.body).toEqual(emptyTessBatch(2));
    const view = new DataView(batch.body!.buffer);
    expect([view.getUint32(0, true), view.getUint32(4, true), view.getUint32(8, true), view.getUint32(12, true), view.getUint32(16, true)]).toEqual([0x42534554, 1, 2, 0, 0]);
    expect(await post('/__tess_cache/batch', '[]')).toMatchObject({ status: 400, json: { error: 'bad batch request' } });
    expect(await post(`/__tess_cache/${sha('aa')}-t4-p4.tess`, new Uint8Array([1, 2, 3]))).toEqual({ status: 204, headers: { 'content-length': '0' } });
    expect(await post('/__tess_cache/..%2Fx.tess', new Uint8Array([1]))).toMatchObject({ status: 403 });
  });
  it('saves a sketch through the context, guards every POST, and refuses the routes a hosted build has not', async () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3]);
    expect((await post('/__cad/sketches', png, { name: 'bracket-sketch.png' })).json).toEqual({ ok: true, path: 'https://objects.example/sketch/bracket-sketch.png-11.png' });
    expect(await post('/__cad/sketches', new Uint8Array([1, 2, 3]), { name: 'x' })).toMatchObject({ status: 400, json: { ok: false } });
    expect(await post('/__cad/sketches', png, { name: 'x' }, {})).toMatchObject({ status: 403, json: { error: "missing x-cadgen-viewer header (cross-site POST blocked); send 'x-cadgen-viewer: 1'" } });
    expect((await post('/__cad/artifact', undefined, { file: '/STEP/bracket.step' })).json).toEqual({ ok: true, state: 'compiled' });
    expect(await post('/__cad/artifact', undefined, { file: '/STEP/missing.step' })).toMatchObject({ status: 500, json: { ok: false, state: 'failed' } });
    for (const path of ['/__cad/surfaces', '/__cad/surfaces/cancel', '/__cad/pick', '/__cad/reveal', '/__cad/clipboard', '/__cad/shutdown', '/__cad/recents', '/__cad/analytics', '/__cad/analytics/activity']) {
      expect(await post(path, '{}')).toMatchObject({ status: 404, json: { ok: false, error: 'Not found' } });
    }
    expect(await post('/__cad/nothing', '{}')).toMatchObject({ status: 405, headers: { allow: 'POST' } });
    expect(await get('/__cad/server', {}, 'DELETE')).toMatchObject({ status: 405, headers: { allow: 'GET, HEAD, POST' } });
  });
});
