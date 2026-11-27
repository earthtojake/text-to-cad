// The build kernel in a Worker (module): Pyodide, the kernel's binding, build123d and cad's own build (../kernel.mjs).
// Requests `{ id, op, ...args }`, replies `{ id, ok, result, ms }` or `{ id, ok: false, error }`:
//   start  { base, cad, kernelPy, pins }  -> { timings, heapBytes, shims }   (base: where the packages are; the rest URLs)
//   build | withValues | preview          -> ../kernel.mjs's answers (an .xbf's bytes transferred)
// Served by serve.mjs, which puts this folder at / and its parent (kernel.mjs) at /host/.
import { loadKernel } from "/host/kernel.mjs";

let kernel = null;

async function handle(message) {
  if (message.op === "start") {
    const [pins, kernelPy, cad] = await Promise.all([
      fetch(message.pins).then((r) => r.json()), fetch(message.kernelPy).then((r) => r.text()),
      fetch(message.cad).then((r) => r.arrayBuffer()),
    ]);
    kernel = await loadKernel({ base: message.base, pins, cad: new Uint8Array(cad), kernelPy,
      stdout: (line) => console.log(line), stderr: (line) => console.warn(line) });
    return { timings: kernel.timings, heapBytes: kernel.heapBytes(), shims: kernel.shims };
  }
  if (!kernel) throw new Error("the kernel has not started");
  if (message.op === "build") {
    const built = kernel.build(message.request);
    return { ...built, heapBytes: kernel.heapBytes() };
  }
  if (message.op === "withValues") return kernel.withValues(message.request);
  if (message.op === "preview") return kernel.preview(message.request);
  throw new Error("unknown op " + message.op);
}

self.onmessage = async (event) => {
  const started = performance.now();
  try {
    const result = await handle(event.data);
    const transfer = result?.xbf?.buffer ? [result.xbf.buffer] : [];
    self.postMessage({ id: event.data.id, ok: true, result, ms: performance.now() - started }, transfer);
  } catch (error) {
    self.postMessage({ id: event.data.id, ok: false, error: String(error?.message || error) });
  }
};
self.postMessage({ ready: true });
