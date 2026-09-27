import assert from "node:assert/strict";
import test from "node:test";

import { loadGlbMeshDataInWorker } from "./glbMeshWorkerClient.js";
import { meshDataTransferList } from "./meshTransfer.js";

test("GLB mesh worker client falls back when Worker is unavailable", () => {
  assert.equal(loadGlbMeshDataInWorker("/mesh.glb"), null);
});

test("mesh transfer list includes unique non-empty typed-array buffers", () => {
  const shared = new ArrayBuffer(16);
  const transferList = meshDataTransferList({
    vertices: new Float32Array(shared),
    normals: new Float32Array(shared),
    indices: new Uint32Array([0, 1, 2]),
    colors: new Float32Array(0),
    cadEdgePositions: new Float32Array([0, 0, 0, 1, 0, 0]),
    cadEdgeIndices: new Uint32Array([0, 1])
  });

  assert.equal(transferList.length, 4);
  assert.equal(transferList[0], shared);
});

test('worker receives provider-owned transfer tickets and brokers nested resource reads', async t => {
  const { retainGlbMeshWorker } = await import('./glbMeshWorkerClient.js');
  const original = globalThis.Worker;
  let worker;
  globalThis.Worker = class {
    listeners = {}; messages = [];
    constructor() { worker = this; }
    addEventListener(type, callback) { this.listeners[type] = callback; }
    postMessage(message, transfer) { this.messages.push({message, transfer}); }
    terminate() {}
  };
  const release = retainGlbMeshWorker();
  t.after(() => { release(); globalThis.Worker = original; });
  const bytes = new ArrayBuffer(4), nested = new ArrayBuffer(8);
  const calls = [];
  const resources = {
    workerTicket: async url => { calls.push(['ticket', url]); return {kind:'bytes',bytes}; },
    resolveDependency: (source, ref) => { calls.push(['resolve', source, ref]); return 'private:mesh'; },
    readBytes: async (url, options) => { calls.push(['read',url, options.maxBytes]); return nested; },
  };
  const result = loadGlbMeshDataInWorker('private:document', {resources});
  await new Promise(resolve => setImmediate(resolve));
  const first = worker.messages[0];
  assert.equal(first.message.resource.bytes, bytes);
  assert.deepEqual(first.transfer, [bytes]);
  worker.listeners.message({data:{type:'resource', id:first.message.id, resourceId:7, reference:'mesh.bin'}});
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(worker.messages[1], {message:{type:'resource',resourceId:7,bytes:nested},transfer:[nested]});
  assert.deepEqual(calls, [['ticket','private:document'],['resolve','private:document','mesh.bin'],['read','private:mesh',64*1024*1024]]);
  worker.listeners.message({data:{id:first.message.id,ok:true,meshData:{done:true}}});
  assert.deepEqual(await result,{done:true});
});
