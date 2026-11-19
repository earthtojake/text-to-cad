import assert from "node:assert/strict";
import test from "node:test";
import { createPickClaims } from "./xbfLayers.js";

// An app layer's claims on the model's clicks (`XbfRendererOptions.layers`): offered in the order
// the layers claimed, until one takes the click, never to a layer that let go, and a click no
// layer takes is Select's.
test("a click goes to the first layer that takes it, and to Select when none does", () => {
  const claims = createPickClaims();
  const heard = [];
  const hit = { id: "f:plate.top", kind: "face" };
  const release = claims.claim(found => { heard.push(["first", found]); return false; });
  claims.claim(found => { heard.push(["second", found]); return true; });
  claims.claim(() => { heard.push(["third"]); return true; });
  assert.equal(claims.offer(hit, { multiSelect: false }), true);
  assert.deepEqual(heard, [["first", hit], ["second", hit]]);

  release();
  heard.length = 0;
  assert.equal(claims.offer(null, { multiSelect: true }), true);
  assert.deepEqual(heard, [["second", null]]);

  const none = createPickClaims();
  none.claim(() => undefined);
  assert.equal(none.offer({ id: "plate" }, { multiSelect: false }), false);
});
