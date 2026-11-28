// A Worker running the view core. Module worker: new Worker("worker.js", { type: "module" }).
//
// Protocol (structured clone; ArrayBuffers are transferred):
//   request  { id, op, ...args }
//   reply    { id, ok: true, result, ms }  |  { id, ok: false, error, fault?, gone? }  (fault: the module faulted, below;
//            gone: the doc asked of is not open, as after a fault)
// ops:
//   init   { url } | { module }          -> { compileMs, fetchMs, instantiateMs, memoryBytes, occt }
//          (`module`: a WebAssembly.Module the page compiled once, for several workers)
//   open   { bytes: Uint8Array, stem? }  -> { doc }            (bytes is transferred in; stem: the file's, which
//          names the document where the file does not)
//   structureBytes|shapeBytes|mesh|groupsBytes|elementsBytes|measureBytes  { doc, part } -> Uint8Array
//   factBytes { doc, part, kind, ordinal } -> Uint8Array
//   structure|groups|elements|measure|fact -> parsed JSON (same args as the *Bytes forms)
//   exportBytes { doc, format }          -> Uint8Array: the document as a file (format: step, stl, threemf, glb)
//   close  { doc }
//   memory {}                            -> { memoryBytes }
// A call the module faults on (a WebAssembly trap) is refused, and the module is started again from its compiled
// code: every doc opened before is let go (it answers "no such doc"), and the page opens what it needs again.
// `ms` is the time the worker spent in the call. Once its handler is set the worker says so, once: { ready: true }
// (a page waits for it before its first request, so none is sent to a worker still loading its modules).
import { Core, isFault } from "./viewcore.js";

let core = null;
const docs = new Map();
let next = 1;

const BINARY = new Set(["exportBytes", "structureBytes", "shapeBytes", "mesh", "groupsBytes", "elementsBytes", "measureBytes", "factBytes"]);
const JSONOPS = new Set(["structure", "groups", "elements", "measure", "fact"]);

async function handle(m) {
  switch (m.op) {
    case "init": {
      core = await Core.load(m.module || m.url);
      return { compileMs: core.compileMs, fetchMs: core.fetchMs, instantiateMs: core.instantiateMs,
               memoryBytes: core.memoryBytes, occt: core.occtVersion };
    }
    case "open": {
      const doc = core.openXbf(m.bytes, m.stem);
      const id = next++;
      docs.set(id, doc);
      return { doc: id };
    }
    case "close": docs.get(m.doc)?.close(); docs.delete(m.doc); return null;
    case "memory": return { memoryBytes: core.memoryBytes };
    default: {
      const doc = docs.get(m.doc);
      if (!doc) throw Object.assign(new Error("no such doc " + m.doc), { gone: true });
      if (BINARY.has(m.op) || JSONOPS.has(m.op)) {
        const args = m.op === "structure" || m.op === "structureBytes" ? [] :
          m.op === "fact" || m.op === "factBytes" ? [m.part, m.kind, m.ordinal] :
          m.op === "exportBytes" ? [m.format] : [m.part];
        return doc[m.op](...args);
      }
      throw new Error("unknown op " + m.op);
    }
  }
}

// One request at a time, in the order they came: a request that came while the module is started again after a fault
// waits for the fresh one.
let queue = Promise.resolve();
self.onmessage = (e) => { queue = queue.then(() => answer(e)); };

async function answer(e) {
  const m = e.data;
  const t = performance.now();
  try {
    const result = await handle(m);
    const transfer = result instanceof Uint8Array ? [result.buffer] : [];
    self.postMessage({ id: m.id, ok: true, result, ms: performance.now() - t }, transfer);
  } catch (err) {
    let error = String(err && err.message || err);
    if (core && isFault(err)) {
      docs.clear();
      try {
        await core.renew();
        error = `the view core faulted (${error}) and was started again; the documents opened before are let go`;
      } catch (again) {
        core = null;
        error = `the view core faulted (${error}) and could not be started again: ${again && again.message || again}`;
      }
    }
    self.postMessage({ id: m.id, ok: false, error, ...(core && isFault(err) ? { fault: true } : {}), ...(err?.gone ? { gone: true } : {}) });
  }
}

self.postMessage({ ready: true });
