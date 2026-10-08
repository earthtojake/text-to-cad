import assert from "node:assert/strict";
import test from "node:test";
import { createCadClient, SurfaceResolutionError } from "@text-to-cad/core/client";
import { isTessellationCacheProbeMissError } from "@text-to-cad/core/lib/surf/tessellationCache.js";
import { createSurfaceTicketBatches, createTessellationBodyBatches } from "./packageBatchReads.js";
import { createInitialDisplayPlans } from "../../../render/initialDisplayLod.js";
import { TEST_TESSELLATION_LADDER, installTestTessellationLadder } from "@text-to-cad/core/lib/surf/testing.js";

// The ladder a cadgen server publishes, installed as a host installs it.
installTestTessellationLadder();

const KIB = 1024, MIB = 1024 * KIB;
const cids = count => Array.from({ length: count }, (_, index) => `c${index}`);
const rowFor = (cid, byteLength = 100 * KIB) => ({ object: `object-${cid}`, byteLength, surfaceInput: `input-${cid}` });
const bodyFor = row => new Uint8Array(row.byteLength).fill(Number(row.object.slice(8)) % 251);
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

// A server's batch read: the bodies of the rows asked for, as views into ONE container, as the
// real TESB decode hands them back.
function batchServer({ answer = rows => rows.map(bodyFor) } = {}) {
  const reads = [];
  return {
    reads,
    readMany: async (rows, { maxBytes }) => {
      reads.push({ count: rows.length, maxBytes });
      const bodies = answer(rows);
      if (!bodies) return null;
      const container = new Uint8Array(bodies.reduce((sum, body) => sum + (body?.byteLength || 0), 0));
      let offset = 0;
      return bodies.map((body) => {
        if (!body) return null;
        container.set(body, offset);
        offset += body.byteLength;
        return container.subarray(offset - body.byteLength, offset);
      });
    },
  };
}

test("bodies are read in batches growing from the first publish to the server's bounds, one batch ahead of the lanes", async () => {
  const order = cids(600);
  const rows = new Map(order.map(cid => [cid, rowFor(cid)]));
  const server = batchServer();
  const batches = createTessellationBodyBatches({ order, rowOf: cid => rows.get(cid), readMany: server.readMany });
  const first = await batches.take("c0", rows.get("c0"));
  // The first batch is the first publish's eight; the next is read with it.
  assert.deepEqual(server.reads.map(read => read.count), [8, 16]);
  assert.equal(first.byteOffset, 0, "a body of its own, to transfer to a worker");
  assert.equal(first.buffer.byteLength, rows.get("c0").byteLength);
  assert.deepEqual(first, bodyFor(rows.get("c0")));
  // Lanes, eight at a time, in load order.
  for (let start = 1; start < order.length; start += 8) {
    await Promise.all(order.slice(start, start + 8).map(async (cid) => {
      assert.deepEqual(await batches.take(cid, rows.get(cid)), bodyFor(rows.get(cid)));
    }));
  }
  assert.deepEqual(server.reads.map(read => read.count), [8, 16, 32, 64, 128, 256, 96]);
  assert.equal(server.reads[0].maxBytes, 12 + 8 * (4 + 100 * KIB), "bounded by its own framed size");
  assert.deepEqual(batches.stats(), { batches: 7, components: 600, refused: 0, live: 0 });
});

test("a batch stays under 32 MiB, and a body no batch can carry is left to its lane", async () => {
  const order = cids(40);
  const rows = new Map(order.map(cid => [cid, rowFor(cid, cid === "c3" ? 40 * MIB : 3 * MIB)]));
  const server = batchServer();
  const batches = createTessellationBodyBatches({ order, rowOf: cid => rows.get(cid), readMany: server.readMany });
  for (const cid of order) {
    const body = await batches.take(cid, rows.get(cid));
    assert.equal(body === null, cid === "c3");
  }
  // 8 MiB, 16 MiB and then 32 MiB of 3 MiB bodies: two, five and ten to a batch.
  assert.deepEqual(server.reads.map(read => read.count), [2, 5, 10, 10, 10, 2]);
  assert.ok(server.reads.every(read => read.maxBytes <= 32 * MIB));
});

test("a transport's ceiling bounds every batch, a body over it is left to its lane, and a higher one is the server's bound", async () => {
  for (const [ceiling, counts, alone] of [
    // 8 MiB: two 3 MiB bodies to a batch from the first, and the 9 MiB one read alone.
    [8 * MIB, [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1], "c3"],
    // Above 32 MiB: the server's bound, as with none (8, 16 and then 32 MiB batches).
    [64 * MIB, [2, 3, 10, 10, 10, 5], ""],
  ]) {
    const order = cids(40);
    const rows = new Map(order.map(cid => [cid, rowFor(cid, cid === "c3" ? 9 * MIB : 3 * MIB)]));
    const server = batchServer();
    const batches = createTessellationBodyBatches({ order, rowOf: cid => rows.get(cid), readMany: server.readMany, maxBytes: ceiling });
    for (const cid of order) assert.equal(await batches.take(cid, rows.get(cid)) === null, cid === alone);
    assert.deepEqual(server.reads.map(read => read.count), counts);
    assert.ok(server.reads.every(read => read.maxBytes <= Math.min(ceiling, 32 * MIB)));
  }
});

test("a batch is charged before it is read and released with its last body; a refused charge reads nothing", async () => {
  const order = cids(30);
  const rows = new Map(order.map(cid => [cid, rowFor(cid)]));
  const server = batchServer();
  const charged = new Map();
  let refuse = false, next = 0;
  const batches = createTessellationBodyBatches({ order, rowOf: cid => rows.get(cid), readMany: server.readMany,
    reserve: (bytes) => {
      if (refuse) return { ok: false };
      const token = `t${next++}`;
      charged.set(token, bytes);
      return { ok: true, token };
    },
    release: token => charged.delete(token) });
  for (const cid of order.slice(0, 7)) await batches.take(cid, rows.get(cid));
  assert.deepEqual([...charged.keys()], ["t0", "t1"], "the first batch and the one read with it");
  assert.equal(charged.get("t0"), 12 + 8 * (4 + 100 * KIB));
  await batches.take("c7", rows.get("c7"));
  assert.deepEqual([...charged.keys()], ["t1"], "the first batch's last body released its charge");
  // The envelope is full when the third batch is formed: it reads nothing and its lanes read alone.
  refuse = true;
  for (const cid of order.slice(8, 24)) await batches.take(cid, rows.get(cid));
  assert.equal(await batches.take("c24", rows.get("c24")), null);
  assert.deepEqual(server.reads.map(read => read.count), [8, 16]);
  assert.equal(batches.stats().refused, 1);
  assert.equal(charged.size, 0);
  batches.dispose();
});

test("an entry a batch could not read is a probe miss for that component alone; a failed batch read leaves each to its lane", async () => {
  const order = cids(8);
  const rows = new Map(order.map(cid => [cid, rowFor(cid)]));
  let failAll = false;
  const server = batchServer({ answer: rows => (failAll ? null : rows.map(row => (row.object === "object-c2" ? null : bodyFor(row)))) });
  const batches = createTessellationBodyBatches({ order, rowOf: cid => rows.get(cid), readMany: server.readMany });
  await assert.rejects(batches.take("c2", rows.get("c2")), isTessellationCacheProbeMissError);
  assert.deepEqual(await batches.take("c3", rows.get("c3")), bodyFor(rows.get("c3")));
  // A row that is not the one batched (a fresh probe after a miss) reads alone.
  assert.equal(await batches.take("c4", { ...rows.get("c4"), object: "object-other" }), null);
  failAll = true;
  const later = createTessellationBodyBatches({ order, rowOf: cid => rows.get(cid), readMany: server.readMany });
  assert.equal(await later.take("c0", rows.get("c0")), null);
});

test("a cold component, a payload already held and a plan not yet known are not batched", async () => {
  const order = cids(12);
  const rows = new Map(order.map(cid => [cid, rowFor(cid)]));
  const known = new Set(order.slice(0, 6));
  const server = batchServer();
  const batches = createTessellationBodyBatches({ order, readMany: server.readMany,
    rowOf: cid => (!known.has(cid) ? undefined : cid === "c1" ? null : rows.get(cid)),
    skip: cid => cid === "c2" });
  assert.notEqual(await batches.take("c0", rows.get("c0")), null);
  // c1 is cold and c2 held: c0, c3, c4, c5 were read; the batch stopped where plans ran out.
  assert.deepEqual(server.reads.map(read => read.count), [4]);
  assert.equal(await batches.take("c2", rows.get("c2")), null);
  for (const cid of order.slice(6)) known.add(cid);
  assert.notEqual(await batches.take("c6", rows.get("c6")), null);
  assert.deepEqual(server.reads.map(read => read.count), [4, 6]);
});

test("the first eight cold components resolve alone, the rest up to 64 to a request, each the moment its own row is ready", async () => {
  const order = cids(200);
  const requests = [];
  const resolve = (requested, { onReady }) => new Promise((done) => {
    const request = { requested, onReady, done };
    requests.push(request);
  });
  const finish = (request) => {
    for (const { cid } of request.requested) request.onReady(cid, { surfUrl: `/surf/${cid}` });
    request.done(new Map(request.requested.map(({ cid }) => [cid, { surfUrl: `/surf/${cid}` }])));
  };
  const tickets = createSurfaceTicketBatches({ order, resolve,
    needs: cid => ({ surfaceInput: `input-${cid}`, surfaceObject: undefined }) });
  const first = tickets.ticket("c0", {});
  await tick();
  // Eight lone requests are out, as eight lanes made them; the rest wait for room.
  assert.deepEqual(requests.map(request => request.requested.length), [1, 1, 1, 1, 1, 1, 1, 1]);
  finish(requests[0]);
  assert.deepEqual(await first, { surfUrl: "/surf/c0" });
  await tick();
  assert.equal(requests.length, 9);
  assert.equal(requests[8].requested.length, 64);
  // A row ready before its request has finished answers its component at once.
  const early = tickets.ticket("c8", {});
  requests[8].onReady("c8", { surfUrl: "/surf/c8" });
  assert.deepEqual(await early, { surfUrl: "/surf/c8" });
  for (const request of requests.slice(1, 8)) finish(request);
  await tick();
  assert.deepEqual(requests.map(request => request.requested.length), [1, 1, 1, 1, 1, 1, 1, 1, 64, 64, 64]);
  assert.equal(tickets.stats().components, 200);
});

test("a surface request that fails fails each of its components still waiting", async () => {
  const order = cids(20);
  const failure = new Error("surface derivation failed for c12");
  const tickets = createSurfaceTicketBatches({ order, alone: 0,
    needs: cid => ({ surfaceInput: `input-${cid}` }),
    resolve: async (requested, { onReady }) => { onReady("c0", { surfUrl: "/surf/c0" }); throw failure; } });
  assert.deepEqual(await tickets.ticket("c0", {}), { surfUrl: "/surf/c0" });
  await assert.rejects(tickets.ticket("c12", {}), failure);
});

// One component cadgen could not mesh fails alone, with its own error: the components beside it in
// its request, ready in the same response (before or after it), are answered.
test("a component that failed in its request fails alone; the ready ones beside it are answered", async () => {
  const hex = c => c.repeat(64);
  const view = { tree: hex("a"), viewId: hex("b"), surfaceProducer: { scheme: 1 } };
  const inputs = { c0: hex("1"), bad: hex("2"), c2: hex("3") };
  const object = hex("e");
  const ready = cid => ({ surfaceInput: inputs[cid], state: "ready", surfaceObject: object, byteLength: 10,
    url: `/__cad/store?tree=${view.tree}&surfaceInput=${inputs[cid]}&object=${object}`,
    selectors: { object: hex("5"), byteLength: 10, url: `/__cad/store?tree=${view.tree}&surfaceInput=${inputs[cid]}&object=${hex("5")}` } });
  const client = createCadClient({ fetch: async () => new Response(JSON.stringify({ viewId: view.viewId, components: {
    c0: ready("c0"),
    bad: { surfaceInput: inputs.bad, state: "failed", error: "component bad: OCCT did not mesh 2 face(s)", code: "mesh" },
    c2: ready("c2"),
  } }), { headers: { "content-type": "application/json" } }) });
  const order = ["bad", "c0", "c2"];
  const tickets = createSurfaceTicketBatches({ order, alone: 0,
    needs: cid => ({ surfaceInput: inputs[cid] }),
    resolve: (requested, options) => client.resolveSurfaceComponents(view, requested, options) });
  const [bad, c0, c2] = await Promise.allSettled(order.map(cid => tickets.ticket(cid, {})));
  assert.equal(tickets.stats().requests, 1);
  assert.equal(bad.status, "rejected");
  assert.ok(bad.reason instanceof SurfaceResolutionError);
  assert.deepEqual([bad.reason.cid, bad.reason.code, bad.reason.message], ["bad", "mesh", "component bad: OCCT did not mesh 2 face(s)"]);
  assert.deepEqual([c0.status, c0.value?.surfaceObject, c2.status, c2.value?.surfaceObject],
    ["fulfilled", object, "fulfilled", object]);
  client.dispose();
});

test("initial plans probe the standard tier a chunk at a time, growing from eight to 256", async () => {
  const components = cids(747).map(cid => [cid, { surfaceInput: `input-${cid}` }]);
  const calls = [];
  // Standard entries for the even components; nothing for the odd ones, which are cold.
  const plans = createInitialDisplayPlans({ components, maxInFlightBytes: 256 * MIB,
    probeEntries: async (inputs, tessellation) => {
      calls.push([tessellation, inputs.length]);
      return new Map(inputs.filter(input => Number(input.slice(7)) % 2 === 0)
        .map(input => [input, { object: `o-${input}`, surfaceObject: "s", byteLength: KIB, decodedBytes: KIB }]));
    } });
  assert.equal(plans.peek("c0"), undefined);
  assert.equal((await plans.plan("c0")).plan.level, 1);
  assert.equal(await plans.plan("c1"), null, "a component the store has no standard mesh for is cold");
  for (const [cid] of components) await plans.plan(cid);
  assert.deepEqual(calls.map(([, count]) => count), [8, 16, 32, 64, 128, 256, 243]);
  const standard = TEST_TESSELLATION_LADDER.levels[TEST_TESSELLATION_LADDER.defaultLevel];
  assert.ok(calls.every(([tessellation]) => JSON.stringify(tessellation) === JSON.stringify(standard)),
    "no tier but the standard one is asked");
  assert.equal(plans.peek("c2").cacheProbe.object, "o-input-c2");
  assert.equal(plans.peek("c3"), null);
});

test("a load that is aborted, or over, asks nothing more ahead and leaves no component waiting", async () => {
  const order = cids(100);
  const sent = [];
  const controller = new AbortController();
  const tickets = createSurfaceTicketBatches({ order, alone: 0, inFlight: 1, signal: controller.signal,
    needs: cid => ({ surfaceInput: `input-${cid}` }),
    resolve: (requested, { signal }) => new Promise((_, reject) => {
      sent.push(requested.length);
      signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
    }) });
  const first = tickets.ticket("c0", {});
  const queued = tickets.ticket("c70", {});
  await tick();
  assert.deepEqual(sent, [64], "one request out, the next formed behind it");
  controller.abort();
  await assert.rejects(first, { name: "AbortError" });
  await assert.rejects(queued, { name: "AbortError" }, "the request never sent fails its components too");
  await tick();
  assert.deepEqual(sent, [64], "and nothing more is sent");
});

test("nothing is probed ahead of the first chunk until the first body read is past", async () => {
  const components = cids(100).map(cid => [cid, { surfaceInput: `input-${cid}` }]);
  const probed = [];
  let pastFirstRead;
  const plans = createInitialDisplayPlans({ components, maxInFlightBytes: 256 * MIB,
    readAheadAfter: new Promise(resolve => { pastFirstRead = resolve; }),
    probeEntries: async (inputs) => { probed.push(inputs.length); return new Map(inputs.map(input => [input,
      { object: `o-${input}`, surfaceObject: "s", byteLength: KIB, decodedBytes: KIB }])); } });
  await plans.plan("c0");
  await tick();
  assert.deepEqual(probed, [8], "the first geometry's probe runs alone");
  pastFirstRead();
  await tick();
  assert.deepEqual(probed, [8, 16, 32], "then the two chunks after it");
});
