import test from "node:test";
import assert from "node:assert/strict";
import { resolveSurfaceComponents } from "./surfaceResolution.js";
test("surface resolution delegates domain inputs to the supplied service", async () => {
  const descriptor = {}, requested = [], signal = new AbortController().signal;
  const tickets = new Map();
  const client = { resolveSurfaceComponents(view, components, options) {
    assert.equal(view, descriptor); assert.equal(components, requested); assert.equal(options.signal, signal); return tickets;
  } };
  assert.equal(await resolveSurfaceComponents(descriptor, requested, {client, signal}), tickets);
  assert.throws(() => resolveSurfaceComponents(descriptor, requested), /workspace service/);
});
