import assert from "node:assert/strict";
import test from "node:test";

// "Importing a package starts no polling, workers or host storage writes" (README): a module
// that keeps a process-wide ledger publishes its diagnostics from a mounted viewer, not at import.
// The GPU device is one for every view on the page -- the engine document's (an .xbf's, a STEP's)
// as every other renderer's -- and its read-only seam (`window.__cadGpuDevice`) is written once a
// view acquires the device.
test("importing the viewer's GPU device writes nothing onto the page", async () => {
  const page = {};
  globalThis.window = page;
  try {
    const { gpuDeviceSupported } = await import("./kit/viewport/gpuDevice.js");
    assert.equal(typeof gpuDeviceSupported(), "boolean");
    assert.deepEqual(Object.keys(page), []);
  } finally {
    delete globalThis.window;
  }
});
