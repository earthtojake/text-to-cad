import assert from "node:assert/strict";
import test from "node:test";

// "Importing a package starts no polling, workers or host storage writes" (README): a module
// that keeps a process-wide ledger publishes its diagnostics from a mounted viewer, not at import.
test("importing the viewer's memory ledger writes nothing onto the page", async () => {
  const page = {};
  globalThis.window = page;
  try {
    const { viewerMemoryPolicy } = await import("./step/render/viewerMemoryPolicy.js");
    assert.deepEqual(Object.keys(page), []);
    assert.equal(viewerMemoryPolicy.snapshot().reservationCount, 0);
  } finally {
    delete globalThis.window;
  }
});
