import assert from "node:assert/strict";
import test from "node:test";

import { snapshotImplicitCadOutputOptions } from "./snapshot.js";

test("snapshot output options merge job and output settings", () => {
  const options = snapshotImplicitCadOutputOptions({
    output: "fallback.png",
    width: 800,
    height: 600,
    camera: "front",
    appearance: "workbench",
    graphics: { detail: 0.5, shadows: false },
    render: { transparent: false }
  }, {
    path: "preview.png",
    width: 1200,
    camera: "top",
    graphics: { shadows: true },
    render: { transparent: true }
  });

  assert.deepEqual(options, {
    path: "preview.png",
    width: 1200,
    height: 600,
    camera: "top",
    appearance: "workbench",
    graphics: { detail: 0.5, shadows: true },
    render: { transparent: true }
  });
});
