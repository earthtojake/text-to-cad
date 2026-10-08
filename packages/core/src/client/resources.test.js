import test from 'node:test';
import assert from 'node:assert/strict';
import { createHttpCadResourceProvider, readCadWorkerTicket } from './resources.js';
import { createCadClient } from './client.js';
import { loadRenderJson, peekRenderJson } from '../lib/renderAssetClient.js';

test('injected resource reads and URL caches remain isolated between workspace providers', async () => {
  const calls = [];
  const provider = name => createHttpCadResourceProvider({fetch: async url => {
    calls.push([name, url]); return Response.json({name});
  }});
  const a = provider('a'), b = provider('b');
  assert.deepEqual(await loadRenderJson('/same.json', {resources:a}), {name:'a'});
  assert.equal(peekRenderJson('/same.json', {resources:b}), null);
  assert.deepEqual(await loadRenderJson('/same.json', {resources:b}), {name:'b'});
  assert.deepEqual(calls, [['a','/same.json'], ['b','/same.json']]);
});

test('custom transfers use bounded owned bytes; ordinary HTTP keeps its URL worker path', async () => {
  const calls = [];
  const custom = createHttpCadResourceProvider({fetch: async url => {
    calls.push(url); return new Response(new Uint8Array([1,2,3]));
  }});
  const ticket = await custom.workerTicket('/component.surf', {maxBytes:3});
  assert.equal(ticket.kind, 'bytes');
  assert.deepEqual([...new Uint8Array(await readCadWorkerTicket(ticket))], [1,2,3]);
  await assert.rejects(custom.workerTicket('/too-large', {maxBytes:2}), /byte limit/);
  const direct = createHttpCadResourceProvider({origin:'https://cad.test'});
  assert.deepEqual(await direct.workerTicket('/part.surf', {maxBytes:5}), {
    kind:'url', url:'https://cad.test/part.surf', maxBytes:5,
  });
  assert.equal(calls.length, 2);
});

test('workspace disposal rejects borrowed provider late replies and does not share cache generations', async () => {
  let finish;
  const provider = createHttpCadResourceProvider({ fetch: () => new Promise(resolve => {finish=resolve;}) });
  const a = createCadClient({resources:provider}), b = createCadClient({resources:provider});
  const read = a.resources.readJson('/late');
  a.dispose();
  finish(Response.json({late:true}));
  await assert.rejects(read, error => error.name === 'AbortError');
  assert.notEqual(a.resources.cacheKey('/same'), b.resources.cacheKey('/same'));
  await assert.rejects(a.resources.workerTicket('/closed'), error => error.name === 'AbortError');
  b.dispose();
});

test('observed backend restart retires resource generation and aborts old reads', async () => {
  let epoch = 'one', finish;
  const client = createCadClient({fetch: async url => url.includes('/__cad/server')
    ? Response.json({identityToken:epoch})
    : new Promise(resolve => {finish=resolve;})});
  await client.serverInfo();
  const before = client.resources.cacheKey('');
  const read = client.resources.readJson('/slow');
  epoch = 'two';
  await client.serverInfo({fresh:true});
  assert.notEqual(client.resources.cacheKey(''), before);
  finish(Response.json({stale:true}));
  await assert.rejects(read, error => error.name === 'AbortError');
  client.dispose();
});

test('HTTP dependency resolution preserves catalog query versions and static packages', () => {
  const resources = createHttpCadResourceProvider({origin:'https://cad.test'});
  const asset = resources.resolveDependency('/__cad/asset?file=/models/model.gltf&v=abc', '../mesh.bin');
  assert.equal(new URL(asset).searchParams.get('file'), '/mesh.bin');
  assert.equal(new URL(asset).searchParams.get('v'), 'abc');
  assert.equal(resources.resolveDependency('/hero/assembly', 'part.surf', {kind:'package'}), 'https://cad.test/hero/assembly/part.surf');
});

test('worker URL tickets retain the configured HTTP cache policy and headers', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({url,options}); return new Response(new Uint8Array([1]));
  });
  const resources = createHttpCadResourceProvider({origin:'https://cad.test',cache:'no-store',headers:{'x-resource':'scoped'}});
  const ticket = await resources.workerTicket('/part.surf');
  assert.deepEqual(ticket,{kind:'url',url:'https://cad.test/part.surf',cache:'no-store',headers:{'x-resource':'scoped'}});
  await readCadWorkerTicket(ticket);
  assert.equal(calls[0].options.cache,'no-store');
  assert.deepEqual(calls[0].options.headers,{'x-resource':'scoped'});
});

test('configured HTTP headers are confined to the provider origin for direct and worker reads', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({url,options}); return new Response(new Uint8Array([1]));
  });
  const resources = createHttpCadResourceProvider({origin:'https://cad.test',headers:{'x-private':'secret'}});
  await resources.readBytes('/own.bin');
  await resources.readBytes('https://external.test/nested.bin');
  assert.deepEqual(calls[0].options.headers,{'x-private':'secret'});
  assert.deepEqual(calls[1].options.headers,{});
  assert.deepEqual((await resources.workerTicket('/own.surf')).headers,{'x-private':'secret'});
  const external = await resources.workerTicket('https://external.test/nested.surf');
  assert.equal(external.headers,undefined);
  await readCadWorkerTicket(external);
  assert.equal(calls[2].options.headers,undefined);
});

test('an issued URL worker ticket cannot publish after its resource generation retires', async t => {
  const { scopeCadResources } = await import('./resources.js');
  const glb = await import('../lib/render/glbMeshWorkerClient.js');
  const stl = await import('../lib/render/stlMeshWorkerClient.js');
  const surf = await import('../lib/surf/surfWorkerClient.js');
  const original = globalThis.Worker;
  const workers=[];
  globalThis.Worker = class {
    events=new Map(); messages=[];
    constructor(){workers.push(this);}
    addEventListener(type,callback){this.events.set(type,callback);}
    postMessage(message){this.messages.push(message);}
    terminate(){}
  };
  t.after(()=>{globalThis.Worker=original;});
  // A surf request carries its component's stored mesh; the resource is its SURF, for selectors.
  const { encodeMeshFixture } = await import('../lib/surf/__tests__/meshFixtures.js');
  const identity = { surfaceInput: 'd'.repeat(64), surfaceObject: 'e'.repeat(64) };
  const entry = encodeMeshFixture({ positions: new Float32Array(9), normals: new Float32Array(9),
    indices: new Uint32Array([0, 1, 2]), faceRanges: [{ ord: 1, color: null, indexStart: 0, indexCount: 3 }], edges: [],
    bounds: { min: [0, 0, 0], max: [0, 0, 0] }, scale: 1 }, identity);
  const loadSurf = (url, options) => surf.loadSurfComponentInWorker(url, { ...options, identity: { ...identity, tessellationEntry: entry.slice() } });
  for (const [load,retain] of [[glb.loadGlbMeshDataInWorker,glb.retainGlbMeshWorker],
    [stl.loadStlMeshDataInWorker,stl.retainStlMeshWorker], [loadSurf,surf.retainSurfWorkerPool]]) {
    const lifetime = new AbortController();
    const resources = scopeCadResources(createHttpCadResourceProvider({origin:'https://cad.test'}),lifetime.signal);
    const release=retain();
    try {
      const pending=load('/part',{resources});
      await new Promise(resolve=>setImmediate(resolve));
      const worker=workers.findLast(value=>value.messages.some(message=>message.resource?.kind==='url'));
      const request=worker.messages.find(message=>message.resource?.kind==='url');
      assert.equal(request.resource.url,'https://cad.test/part');
      const oldSignal=resources.signal;
      resources.invalidate();
      assert.equal(oldSignal.aborted,true);
      await assert.rejects(pending,error=>error.name==='AbortError');
      worker.events.get('message')({data:{id:request.id,ok:true,meshData:{stale:true}}});
      const replacement=load('/new',{resources});
      await new Promise(resolve=>setImmediate(resolve));
      const active=workers.findLast(value=>value.messages.some(message=>message.url==='https://cad.test/new'||message.url==='/new'));
      const next=active.messages.find(message=>message.url==='/new'||message.url==='https://cad.test/new');
      active.events.get('message')({data:{id:next.id,ok:true,meshData:{current:true}}});
      const result=await replacement;
      assert.deepEqual(result.meshData || result,{current:true});
    } finally {lifetime.abort();release();}
  }
});

test('a failed read carries the viewer\'s own reason, with its status', async () => {
  const provider = createHttpCadResourceProvider({ fetch: async () => Response.json(
    { error: 'artifact request failed: The geometry service failed (exit 1).' }, { status: 400 }) });
  await assert.rejects(provider.readJson('/__cad/store?file=a'), error =>
    error.message === 'artifact request failed: The geometry service failed (exit 1).' && error.status === 400);
  const plain = createHttpCadResourceProvider({ fetch: async () => new Response('nope', { status: 404, statusText: 'Not Found' }) });
  await assert.rejects(plain.readJson('/missing'), error => /404 Not Found/.test(error.message) && error.status === 404);
});
