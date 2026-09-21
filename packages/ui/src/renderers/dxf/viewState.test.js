import assert from "node:assert/strict";
import test from "node:test";

import { DXF_VIEW_STATE_KIND, DXF_VIEW_STATE_VERSION, dxfViewStateRecord, readDxfViewState } from "./viewState.js";

const TRANSFORM = { scale: 10.8, offsetX: 60, offsetY: 664 };
const RECORD = { kind: DXF_VIEW_STATE_KIND, version: DXF_VIEW_STATE_VERSION, transform: TRANSFORM };

test("a moved view round-trips", () => {
  const record = dxfViewStateRecord(TRANSFORM, true);
  assert.deepEqual(record, RECORD);
  assert.deepEqual(readDxfViewState(record), TRANSFORM);
});

test("an untouched view stores nothing, so it reopens fitted to whatever pane it lands in", () => {
  assert.equal(dxfViewStateRecord(TRANSFORM, false), null);
  assert.equal(dxfViewStateRecord(null, true), null);
  assert.equal(readDxfViewState(null), null);
  assert.equal(readDxfViewState(undefined), null);
});

test("the 3D DXF viewer's record is not migrated: it reads as nothing stored", () => {
  const old = {
    version: 1, camera: { position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0] },
    display: { mode: "solid" }, inspectorTab: "material", tool: "",
    renderer: { thicknessMm: 4, bends: [{ angleDeg: 75, direction: "up" }], hiddenLayers: ["ENGRAVE"], view: "2d" }
  };
  assert.equal(readDxfViewState(old), null);
});

test("a record with a broken transform is nothing stored, never a half-restored view", () => {
  for (const transform of [null, {}, [1, 2, 3], { scale: 0, offsetX: 1, offsetY: 2 },
    { scale: -3, offsetX: 1, offsetY: 2 }, { scale: 1, offsetX: Number.NaN, offsetY: 2 },
    { scale: 1, offsetX: 1 }]) {
    assert.equal(readDxfViewState({ ...RECORD, transform }), null, JSON.stringify(transform));
  }
  assert.equal(readDxfViewState({ ...RECORD, version: 2 }), null);
  assert.equal(readDxfViewState({ ...RECORD, kind: "cad-view" }), null);
  assert.equal(readDxfViewState("dxf-view"), null);
  assert.equal(readDxfViewState([RECORD]), null);
});

test("the stored transform carries nothing but the three numbers", () => {
  const record = dxfViewStateRecord({ ...TRANSFORM, bounds: [0, 0, 1, 1], file: "plate.dxf" }, true);
  assert.deepEqual(Object.keys(record.transform), ["scale", "offsetX", "offsetY"]);
});
