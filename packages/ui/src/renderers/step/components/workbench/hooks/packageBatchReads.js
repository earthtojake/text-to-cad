// Batched reads for a package's progressive load (`useCadAssets`): one request for many
// components where the loader made one per component, as the snapshot loader reads a package
// (`@text-to-cad/core/common/source.js`). What the loader decides per component -- its tier, its
// admission, its order, when it publishes -- stays the loader's (`packageProgressiveLoad.js`);
// these only group the requests its lanes would make one at a time, in the order they make them.
//
// Batches grow from the size of the loader's first publish to the server's bounds, doubling as
// the publish ceilings do, so the first geometry waits for no more than it did, and each batch is
// read one ahead of the components the lanes are on.

import { SURFACE_REQUEST_MAX_COMPONENTS } from "@text-to-cad/core/client";
import {
  TESS_PROBE_MAX_KEYS,
  TessellationCacheProbeMissError,
  tessBatchMaxBytes,
} from "@text-to-cad/core/lib/surf/tessellationCache.js";
import { PROGRESSIVE_PUBLISH_FIRST_BYTES, PROGRESSIVE_PUBLISH_FIRST_COMPONENTS } from "./packageProgressiveLoad.js";

function abortError() {
  return typeof DOMException === "function"
    ? new DOMException("The operation was aborted.", "AbortError")
    : Object.assign(new Error("The operation was aborted."), { name: "AbortError" });
}

// The TESB container: a 12-byte header, then per entry a u32 length and its 4-byte-padded bytes.
const BATCH_HEADER_BYTES = 12;
const framedEntryBytes = row => 4 + ((Number(row.byteLength) + 3) & ~3);

/**
 * The ceilings of the `index`th batch: the first publish's, doubling up to the server's bounds.
 * `maxBytes` is the transport's ceiling (the cache's `batchMaxBytes`), which can lower the
 * server's byte bound and never raise it (`tessBatchMaxBytes`).
 */
export function batchCeilings(index, {
  firstComponents = PROGRESSIVE_PUBLISH_FIRST_COMPONENTS, firstBytes = PROGRESSIVE_PUBLISH_FIRST_BYTES,
  maxComponents = TESS_PROBE_MAX_KEYS, maxBytes,
} = {}) {
  const growth = 2 ** Math.max(0, Math.min(30, Number(index) || 0));
  return {
    components: Math.max(1, Math.min(maxComponents, firstComponents * growth)),
    bytes: Math.max(1, Math.min(tessBatchMaxBytes(maxBytes), firstBytes * growth)),
  };
}

/**
 * The bodies of a package's warm components, read a batch at a time (`readMany`: one
 * `POST /__tess_cache/batch`) where each lane read its own.
 *
 * `rowOf(cid)` is the component's probed row (its plan's `cacheProbe`), null when it has none to
 * read (cold), undefined while that is not known yet: a batch takes the warm components that
 * follow in load order up to its ceilings and stops at the first unknown one. A component whose
 * framed body alone is over the batch bound, or that needs no body (`skip`: its payload is already
 * held), is left to its lane. A batch's framed bytes are reserved (`reserve`) before it is read and
 * released once each of its components has taken its body or given it up; a refused reservation
 * reads nothing, and its components read their own, under their own admission, as before.
 *
 * `take(cid, row)` answers the component's verified bytes in a buffer of their own, ready to
 * transfer to a worker; null when its lane must read it itself (not batched, the batch read
 * failed, or the row is not the one batched); and throws `TessellationCacheProbeMissError` when
 * the batch was read and this entry was not in it -- the strict read's answer, which the loader
 * retries from fresh metadata. A batch read answered reads the next one, so a read ahead never
 * competes with the one the first geometry waits on.
 */
export function createTessellationBodyBatches({
  order, rowOf, readMany, signal,
  reserve = () => ({ ok: true, token: null }), release = () => {}, skip = () => false,
  ...limits
}) {
  const position = new Map(order.map((cid, index) => [cid, index]));
  const batchOf = new Map();
  const live = new Set();
  let considered = -1;
  let formed = 0;
  let last = null;
  let disposed = false;
  const stats = { batches: 0, components: 0, refused: 0 };

  function retire(batch, member) {
    if (member.done) return;
    member.done = true;
    batchOf.delete(member.cid);
    batch.open -= 1;
    if (batch.open > 0) return;
    // Every component has its body or gave it up: the container goes, and so does its charge.
    batch.read = null;
    live.delete(batch);
    if (batch.token !== null) release(batch.token);
    batch.token = null;
  }

  function formNext() {
    if (disposed) return null;
    const ceilings = batchCeilings(formed, limits);
    const members = [];
    let bytes = BATCH_HEADER_BYTES;
    for (let index = considered + 1; index < order.length; index += 1) {
      const cid = order[index];
      const row = rowOf(cid);
      if (row === undefined) break;
      if (!row || batchOf.has(cid) || skip(cid, row)) { considered = index; continue; }
      const entryBytes = framedEntryBytes(row);
      // A body no batch can carry is its lane's to read, as every body was.
      if (BATCH_HEADER_BYTES + entryBytes > tessBatchMaxBytes(limits.maxBytes)) { considered = index; continue; }
      if (members.length >= ceilings.components || (members.length && bytes + entryBytes > ceilings.bytes)) break;
      members.push({ cid, row, slot: members.length, done: false });
      bytes += entryBytes;
      considered = index;
    }
    if (!members.length) return null;
    const batch = { index: formed, members, bytes, open: members.length, token: null, read: null };
    formed += 1;
    for (const member of members) batchOf.set(member.cid, { batch, member });
    const reservation = reserve(bytes) || { ok: false };
    if (reservation.ok === false) {
      stats.refused += 1;
      batch.read = Promise.resolve(null);
    } else {
      batch.token = reservation.token ?? null;
      stats.batches += 1;
      stats.components += members.length;
      batch.read = Promise.resolve().then(() => readMany(members.map(member => member.row), { signal, maxBytes: bytes }));
      // Read ahead of the lanes: nobody may be waiting on it when it fails.
      batch.read.catch(() => {});
    }
    live.add(batch);
    last = batch;
    return batch;
  }

  function formThrough(cid) {
    const at = position.get(cid);
    while (!batchOf.has(cid) && at !== undefined && considered < at) {
      if (!formNext()) break;
    }
  }

  async function take(cid, row) {
    if (disposed || !row) return null;
    formThrough(cid);
    const held = batchOf.get(cid);
    if (!held) return null;
    const { batch, member } = held;
    if (member.row.object !== row.object) { retire(batch, member); return null; }
    let entries;
    try {
      entries = await batch.read;
      // The lanes are on this batch, and it is here: read the next one now.
      if (batch === last) formNext();
    } finally {
      // The bytes are copied out below or given up: either way this member is done with the batch.
      const entry = Array.isArray(entries) ? entries[member.slot] : null;
      member.bytes = entry ? entry.slice() : null;
      retire(batch, member);
    }
    if (!Array.isArray(entries)) return null;
    if (!member.bytes) throw new TessellationCacheProbeMissError(row);
    const bytes = member.bytes;
    member.bytes = null;
    return bytes;
  }

  return {
    take,
    /** The lane gives up the batched body of `cid` (it is reading afresh). */
    discard(cid) {
      const held = batchOf.get(cid);
      if (held) retire(held.batch, held.member);
    },
    dispose() {
      disposed = true;
      for (const batch of [...live]) for (const member of batch.members) retire(batch, member);
    },
    /** Diagnostics: batches read, the components they carried, and batches the envelope refused. */
    stats: () => ({ ...stats, live: live.size }),
  };
}

/**
 * Exact SURF tickets for a package's cold components, resolved up to `maxComponents` to a
 * `POST /__cad/surfaces` in load order where each lane asked for its own.
 *
 * `needs(cid)` is the component when it must be resolved, false when it need not be (it is warm,
 * or carries its surface), undefined while that is not known yet. The first `alone` components to
 * resolve go one to a request, as their lanes asked before, so the derivations the first geometry
 * waits on still run side by side; the rest go up to `maxComponents` to a request, with up to
 * `inFlight` requests out at once ahead of the lanes. A component's ticket is answered the moment
 * its own row is ready (`onReady`), not when its whole request is. A request that fails fails each
 * of its components still waiting, with its error. Once the load is over, aborted or failed
 * (`dispose`), nothing more is asked ahead: a derivation nobody will draw is not started.
 */
export function createSurfaceTicketBatches({
  order, needs, resolve, signal,
  alone = PROGRESSIVE_PUBLISH_FIRST_COMPONENTS, maxComponents = SURFACE_REQUEST_MAX_COMPONENTS, inFlight = 8,
}) {
  const position = new Map(order.map((cid, index) => [cid, index]));
  const waiting = new Map();
  const queued = [];
  let considered = -1;
  let assigned = 0;
  let running = 0;
  let stopped = false;
  const stats = { requests: 0, components: 0 };
  const idle = () => stopped || signal?.aborted;
  // Requests formed but not sent fail their components at once: nobody is left to send them.
  function abandon(reason) {
    for (const requested of queued.splice(0)) {
      for (const { cid } of requested) {
        const entry = waiting.get(cid);
        if (entry && !entry.done) { entry.done = true; entry.reject(reason); }
      }
    }
  }
  signal?.addEventListener?.("abort", () => abandon(abortError()), { once: true });

  function waiter(cid) {
    let settle;
    const promise = new Promise((resolveTicket, reject) => { settle = { resolve: resolveTicket, reject }; });
    promise.catch(() => {});
    const entry = { promise, ...settle, done: false };
    waiting.set(cid, entry);
    return entry;
  }

  function formNext() {
    const requested = [];
    const size = assigned < alone ? 1 : maxComponents;
    for (let index = considered + 1; index < order.length && requested.length < size; index += 1) {
      const cid = order[index];
      const component = needs(cid);
      if (component === undefined) break;
      considered = index;
      if (!component || waiting.has(cid)) continue;
      waiter(cid);
      requested.push({ cid, surfaceInput: component.surfaceInput, surfaceObject: component.surfaceObject });
    }
    if (!requested.length) return false;
    assigned += requested.length;
    queued.push(requested);
    return true;
  }

  // Ahead of the lanes: as many requests formed and out as may run at once.
  function refill() {
    if (idle()) return;
    while (queued.length + running < inFlight && formNext()) { /* formed */ }
    pump();
  }

  function pump() {
    while (!idle() && running < inFlight && queued.length) {
      const requested = queued.shift();
      running += 1;
      stats.requests += 1;
      stats.components += requested.length;
      const answer = (cid, ticket) => {
        const entry = waiting.get(cid);
        if (!entry || entry.done) return;
        entry.done = true;
        entry.resolve(ticket);
      };
      Promise.resolve()
        .then(() => resolve(requested, { signal, onReady: answer }))
        .then((tickets) => {
          for (const { cid } of requested) {
            const ticket = tickets?.get?.(cid);
            if (ticket) answer(cid, ticket);
            else {
              const entry = waiting.get(cid);
              if (entry && !entry.done) { entry.done = true; entry.reject(new Error(`Surface response omitted ${cid}`)); }
            }
          }
        }, (error) => {
          for (const { cid } of requested) {
            const entry = waiting.get(cid);
            if (entry && !entry.done) { entry.done = true; entry.reject(error); }
          }
        })
        .finally(() => { running -= 1; refill(); });
    }
  }

  return {
    ticket(cid, component) {
      const at = position.get(cid);
      while (!waiting.has(cid) && at !== undefined && considered < at) {
        if (!formNext()) break;
      }
      refill();
      const entry = waiting.get(cid);
      if (entry) return entry.promise;
      // Not one this table knows to batch yet: asked alone, as before.
      return Promise.resolve(resolve([{ cid, surfaceInput: component.surfaceInput, surfaceObject: component.surfaceObject }], { signal }))
        .then((tickets) => {
          const ticket = tickets.get(cid);
          if (!ticket) throw new Error(`Surface response omitted ${cid}`);
          return ticket;
        });
    },
    dispose() { stopped = true; abandon(new Error("The package load is over")); },
    /** Diagnostics: requests made and the components they named. */
    stats: () => ({ ...stats }),
  };
}
