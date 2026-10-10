import assert from "node:assert/strict";
import test from "node:test";
import { chromeStyle, lightColour } from "./paperContrast.js";

test("the chrome stands nearly opaque only over paper the other way round from the theme", () => {
  assert.equal(lightColour("#ffffff"), true);
  assert.equal(lightColour("001023"), false);
  assert.equal(lightColour("white"), null, "a colour it cannot read says nothing");
  const schematic = [{ background: "#f5f4ef" }];
  const board = [{ background: "#001023" }];
  assert.deepEqual(chromeStyle(schematic, true), { "--cad-chrome-alpha": "90%" });
  assert.equal(chromeStyle(schematic, false), undefined);
  assert.deepEqual(chromeStyle(board, false), { "--cad-chrome-alpha": "90%" });
  assert.equal(chromeStyle(board, true), undefined);
  assert.equal(chromeStyle(null, true), undefined);
});
