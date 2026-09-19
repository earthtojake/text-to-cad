import assert from "node:assert/strict";
import test from "node:test";

import { backdropLuminance, documentDeskColor } from "./documentDesk.js";

test("a dark backdrop lifts and a light one settles, both staying on their own side", () => {
  const dark = documentDeskColor("#14171a");
  assert.ok(backdropLuminance(dark) > backdropLuminance("#14171a"), "the desk is lighter than the void");
  assert.ok(backdropLuminance(dark) < 0.5, "and still a dark theme");
  const light = documentDeskColor("#ffffff");
  assert.ok(backdropLuminance(light) < backdropLuminance("#ffffff"), "the desk is darker than white paper");
  assert.ok(backdropLuminance(light) > 0.5, "and still a light theme");
  assert.equal(documentDeskColor("#000"), "#242424");
});

test("an unreadable colour is left alone", () => {
  assert.equal(documentDeskColor("var(--sidebar)"), "var(--sidebar)");
  assert.equal(documentDeskColor(""), "");
  assert.equal(backdropLuminance("nope"), 0);
});
