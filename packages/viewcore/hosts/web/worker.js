// A Worker running the view core. Module worker: new Worker("worker.js", { type: "module" }).
//
// Protocol (structured clone; ArrayBuffers are transferred):
//   request  { id, op, ...args }
//   reply    { id, ok: true, result, ms }  |  { id, ok: false, error }
// ops:
//   init   { url }                       -> { compileMs, fetchMs, instantiateMs, memoryBytes, occt }
//   open   { bytes: Uint8Array }         -> { doc }            (bytes is transferred in)
//   structureBytes|shapeBytes|mesh|groupsBytes|elementsBytes|measureBytes  { doc, part } -> Uint8Array
//   factBytes { doc, part, kind, ordinal } -> Uint8Array
//   structure|groups|elements|measure|fact -> parsed JSON (same args as the *Bytes forms)
//   close  { doc }
//   memory {}                            -> { memoryBytes }
// `ms` is the time the worker spent in the call.
import { Core } from "./viewcore.js";

let core = null;
const docs = new Map();
let next = 1;

const BINARY = new Set(["structureBytes", "shapeBytes", "mesh", "groupsBytes", "elementsBytes", "measureBytes", "factBytes"]);
const JSONOPS = new Set(["structure", "groups", "elements", "measure", "fact"]);

async function handle(m) {
  switch (m.op) {
    case "init": {
      core = await Core.load(m.url);
      return { compileMs: core.compileMs, fetchMs: core.fetchMs, instantiateMs: core.instantiateMs,
               memoryBytes: core.memoryBytes, occt: core.occtVersion };
    }
    case "open": {
      const doc = core.openXbf(m.bytes);
      const id = next++;
      docs.set(id, doc);
      return { doc: id };
    }
    case "close": docs.get(m.doc)?.close(); docs.delete(m.doc); return null;
    case "memory": return { memoryBytes: core.memoryBytes };
    default: {
      const doc = docs.get(m.doc);
      if (!doc) throw new Error("no such doc " + m.doc);
      if (BINARY.has(m.op) || JSONOPS.has(m.op)) {
        const args = m.op === "structure" || m.op === "structureBytes" ? [] :
          m.op === "fact" || m.op === "factBytes" ? [m.part, m.kind, m.ordinal] : [m.part];
        return doc[m.op](...args);
      }
      throw new Error("unknown op " + m.op);
    }
  }
}

self.onmessage = async (e) => {
  const m = e.data;
  const t = performance.now();
  try {
    const result = await handle(m);
    const transfer = result instanceof Uint8Array ? [result.buffer] : [];
    self.postMessage({ id: m.id, ok: true, result, ms: performance.now() - t }, transfer);
  } catch (err) {
    self.postMessage({ id: m.id, ok: false, error: String(err && err.message || err) });
  }
};
