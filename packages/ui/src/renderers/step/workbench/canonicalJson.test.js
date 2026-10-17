import assert from "node:assert/strict";
import test from "node:test";
import { canonicalJson, jsonDigest } from "./canonicalJson.js";

test("equal data is one form and one digest whichever JSON spelled it", () => {
  const sidecar = JSON.parse('{"clips":[{"id":"swing","tracks":[{"times":[0,0.5],"targets":["o:5da881c8dcfe"]}]}]}');
  const annotations = JSON.parse('{"clips":[{"tracks":[{"targets":["o:5da881c8dcfe"],"times":[0,5e-1]}],"id":"swing"}]}');
  assert.equal(canonicalJson(sidecar), canonicalJson(annotations));
  assert.equal(jsonDigest(sidecar), jsonDigest(annotations));
  assert.match(jsonDigest(sidecar), /^[0-9a-f]{16}$/);
});

test("a changed value is another digest", () => {
  const clips = { clips: [{ id: "swing", tracks: [{ times: [0, 1] }] }] };
  assert.notEqual(jsonDigest(clips), jsonDigest({ clips: [{ id: "swing", tracks: [{ times: [0, 2] }] }] }));
  assert.notEqual(jsonDigest(clips), jsonDigest({ clips: [{ id: "sweep", tracks: [{ times: [0, 1] }] }] }));
  assert.notEqual(jsonDigest(null), jsonDigest({}));
});
