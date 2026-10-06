import assert from "node:assert/strict";
import test from "node:test";

import { promptResourceFor, referencePathFor, resourceStem } from "./promptResource.js";

const file = { kind: "workspace-file", path: "/work/STEP/bracket.step", revision: "r1" };

test("without an address a prompt names the file by its path, exactly as the view does", () => {
  assert.equal(promptResourceFor({ id: "local" }, file), file);
  assert.equal(promptResourceFor(null, file), file);
  assert.equal(promptResourceFor({ address: () => "" }, file), file);
  assert.equal(referencePathFor({ id: "local" }, "/work/STEP/bracket.step"), "/work/STEP/bracket.step");
});

test("a host whose files have an address names them by it, revision kept, and the view's own identity untouched", () => {
  const address = path => `https://cad.example/b/k7Qx2${path.replace("/work", "")}`;
  assert.deepEqual(promptResourceFor({ address }, file), { kind: "url", url: "https://cad.example/b/k7Qx2/STEP/bracket.step", revision: "r1" });
  assert.deepEqual(promptResourceFor({ address }, { kind: "workspace-file", path: "/work/a.step" }), { kind: "url", url: "https://cad.example/b/k7Qx2/a.step" });
  assert.equal(referencePathFor({ address }, "/work/STEP/bracket.step"), "https://cad.example/b/k7Qx2/STEP/bracket.step");
  // A resource already named by URL is left as it is.
  const url = { kind: "url", url: "https://elsewhere.example/a.step" };
  assert.equal(promptResourceFor({ address }, url), url);
});

test("a capture is named after the file, from its path or its URL", () => {
  assert.equal(resourceStem(file), "bracket");
  assert.equal(resourceStem({ kind: "url", url: "https://cad.example/b/k7Qx2/STEP/my%20part.step" }), "my part");
  assert.equal(resourceStem({ kind: "url", url: "not a url" }), "not a url");
  assert.equal(resourceStem({}), "view");
});
