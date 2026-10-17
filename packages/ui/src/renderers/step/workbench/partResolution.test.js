import test from "node:test";
import assert from "node:assert/strict";
import { resolveParts } from "./partResolution.js";
test("part resolution delegates domain inputs to the supplied service", async () => {
  const descriptor = {}, requested = [], signal = new AbortController().signal;
  const tickets = new Map();
  const client = { resolveParts(view, components, options) {
    assert.equal(view, descriptor); assert.equal(components, requested); assert.equal(options.signal, signal); return tickets;
  } };
  assert.equal(await resolveParts(descriptor, requested, {client, signal}), tickets);
  assert.throws(() => resolveParts(descriptor, requested), /workspace service/);
});

test("every callback the loader hears through reaches the service, the deriving one too", async () => {
  const onReady = () => {}, onFailed = () => {}, onPending = () => {};
  let seen = null;
  const client = { resolveParts(view, components, options) { seen = options; return new Map(); } };
  await resolveParts({}, [], { client, onReady, onFailed, onPending, tessellation: { chordTolerance: 1, angleTolerance: 1 } });
  assert.equal(seen.onReady, onReady);
  assert.equal(seen.onFailed, onFailed);
  assert.equal(seen.onPending, onPending, "a loading screen hears that cadgen is meshing");
});
