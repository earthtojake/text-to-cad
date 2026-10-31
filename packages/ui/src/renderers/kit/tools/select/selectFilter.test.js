import assert from "node:assert/strict";
import test from "node:test";

import { pickModeOf, selects } from "./selectFilter.js";

const MODES = [
  { id: "all", label: "All", kinds: ["parts", "faces", "edges", "position", "annotation", "measurement"] },
  { id: "faces", label: "Faces", kinds: ["faces"] },
  { id: "edges", label: "Edges", kinds: ["edges"] },
];

test("a filter is the mode whose kinds it picks, in any order, else All", () => {
  assert.equal(pickModeOf(["faces"], MODES).id, "faces");
  assert.equal(pickModeOf(["measurement", "annotation", "position", "edges", "faces", "parts"], MODES).id, "all");
  assert.equal(pickModeOf(["faces", "edges"], MODES).id, "all", "no mode picks two kinds alone");
  assert.equal(pickModeOf([], []), null);
});

test("a filter picks what its mode picks", () => {
  assert.equal(selects(["faces", "measurement"], "measurement"), true);
  assert.equal(selects(["faces"], "measurement"), false);
  assert.equal(selects([], "faces"), false);
});
