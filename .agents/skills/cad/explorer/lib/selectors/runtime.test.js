import assert from "node:assert/strict";
import { test } from "node:test";

import { buildSelectorRuntime } from "./runtime.js";

test("buildSelectorRuntime remaps source part rows onto an assembly occurrence", () => {
  const bundle = {
    manifest: {
      cadRef: "parts/source",
      tables: {
        occurrenceColumns: ["id", "path", "name", "sourceName", "parentId", "transform", "bbox", "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        shapeColumns: ["id", "occurrenceId", "ordinal", "kind", "bbox", "center", "area", "volume", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        faceColumns: ["id", "occurrenceId", "shapeId", "ordinal", "surfaceType", "area", "center", "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags", "params", "triangleStart", "triangleCount"],
        edgeColumns: ["id", "occurrenceId", "shapeId", "ordinal", "curveType", "length", "center", "bbox", "faceStart", "faceCount", "relevance", "flags", "params", "segmentStart", "segmentCount"],
      },
      occurrences: [
        ["o1", "1", null, null, null, null, null, 0, 2, 0, 2, 0, 0],
        ["o1.1", "1.1", null, null, "o1", null, null, 0, 1, 0, 1, 0, 0],
        ["o1.2", "1.2", null, null, "o1", null, null, 1, 1, 1, 1, 0, 0]
      ],
      shapes: [
        ["o1.1.s1", "o1.1", 1, "solid", null, null, 1, 1, 0, 1, 0, 0],
        ["o1.2.s1", "o1.2", 1, "solid", null, null, 1, 1, 1, 1, 0, 0]
      ],
      faces: [
        ["o1.1.f1", "o1.1", "o1.1.s1", 1, "plane", 1, [0, 0, 0], [0, 0, 1], null, 0, 0, 0, 0, {}, 0, 0],
        ["o1.2.f1", "o1.2", "o1.2.s1", 1, "plane", 1, [1, 0, 0], [0, 0, 1], null, 0, 0, 0, 0, {}, 0, 0]
      ],
      edges: []
    },
    buffers: {}
  };

  const runtime = buildSelectorRuntime(bundle, {
    copyCadPath: "parts/root",
    partId: "o1.5",
    remapOccurrenceId: "o1.5"
  });
  const faces = runtime.references.filter((reference) => reference.selectorType === "face");

  assert.deepEqual(faces.map((reference) => reference.displaySelector), ["o1.5.f1", "o1.5.f2"]);
  assert.equal(faces[1].copyText, "@cad[parts/root#o1.5.f2] plane area=1");
  assert.equal(faces[1].pickData.surfaceType, "plane");
  assert.equal(faces[1].pickData.area, 1);
});

test("buildSelectorRuntime remaps native occurrence prefixes onto assembly descendants", () => {
  const bundle = {
    manifest: {
      cadRef: "parts/native",
      tables: {
        occurrenceColumns: ["id", "path", "name", "sourceName", "parentId", "transform", "bbox", "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        shapeColumns: ["id", "occurrenceId", "ordinal", "kind", "bbox", "center", "area", "volume", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        faceColumns: ["id", "occurrenceId", "shapeId", "ordinal", "surfaceType", "area", "center", "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags", "params", "triangleStart", "triangleCount"],
        edgeColumns: ["id", "occurrenceId", "shapeId", "ordinal", "curveType", "length", "center", "bbox", "faceStart", "faceCount", "relevance", "flags", "params", "segmentStart", "segmentCount"],
      },
      occurrences: [
        ["o1", "1", null, null, null, null, null, 0, 2, 0, 2, 0, 0],
        ["o1.1", "1.1", null, null, "o1", null, null, 0, 1, 0, 1, 0, 0],
        ["o1.2", "1.2", null, null, "o1", null, null, 1, 1, 1, 1, 0, 0]
      ],
      shapes: [
        ["o1.1.s1", "o1.1", 1, "solid", null, null, 1, 1, 0, 1, 0, 0],
        ["o1.2.s1", "o1.2", 1, "solid", null, null, 1, 1, 1, 1, 0, 0]
      ],
      faces: [
        ["o1.1.f1", "o1.1", "o1.1.s1", 1, "plane", 1, [0, 0, 0], [0, 0, 1], null, 0, 0, 0, 0, {}, 0, 0],
        ["o1.2.f1", "o1.2", "o1.2.s1", 1, "plane", 1, [1, 0, 0], [0, 0, 1], null, 0, 0, 0, 0, {}, 0, 0]
      ],
      edges: []
    },
    buffers: {}
  };

  const runtime = buildSelectorRuntime(bundle, {
    copyCadPath: "assemblies/root",
    partId: "o9.4",
    remapOccurrencePrefix: {
      sourceRootOccurrenceId: "o1",
      targetRootOccurrenceId: "o9.4.1",
      sourceOccurrenceId: "o1.2"
    }
  });
  const faces = runtime.references.filter((reference) => reference.selectorType === "face");

  assert.deepEqual(faces.map((reference) => reference.displaySelector), ["o9.4.1.2.f2"]);
  assert.equal(runtime.occurrenceIdByRowIndex.get(0), "o1");
  assert.equal(runtime.occurrenceIdByRowIndex.get(1), "o1.1");
  assert.equal(runtime.occurrenceIdByRowIndex.get(2), "o9.4.1.2");
});

test("buildSelectorRuntime exposes v1 GLB face runs from selector buffers", () => {
  const bundle = {
    manifest: {
      cadRef: "parts/source",
      faceProxy: {
        source: "model.glb",
        runsView: "faceRuns",
        runColumns: ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"]
      },
      tables: {
        occurrenceColumns: ["id", "path", "name", "sourceName", "parentId", "transform", "bbox", "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        shapeColumns: ["id", "occurrenceId", "ordinal", "kind", "bbox", "center", "area", "volume", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        faceColumns: ["id", "occurrenceId", "shapeId", "ordinal", "surfaceType", "area", "center", "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags", "params", "triangleStart", "triangleCount"],
        edgeColumns: ["id", "occurrenceId", "shapeId", "ordinal", "curveType", "length", "center", "bbox", "faceStart", "faceCount", "relevance", "flags", "params", "segmentStart", "segmentCount"],
      },
      occurrences: [
        ["o1", "1", null, null, null, null, null, 0, 1, 0, 1, 0, 0]
      ],
      shapes: [
        ["o1.s1", "o1", 1, "solid", null, null, 1, 1, 0, 1, 0, 0]
      ],
      faces: [
        ["o1.f1", "o1", "o1.s1", 1, "plane", 1, [0, 0, 0], [0, 0, 1], null, 0, 0, 0, 0, {}, 2, 4]
      ],
      edges: []
    },
    buffers: {
      faceRuns: new Uint32Array([0, 1, 2, 4, 0])
    }
  };

  const runtime = buildSelectorRuntime(bundle);

  assert.deepEqual(Array.from(runtime.proxy.faceRuns), [0, 1, 2, 4, 0]);
  assert.deepEqual(runtime.proxy.faceRunColumns, ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"]);
  assert.equal(runtime.occurrenceIdByRowIndex.get(0), "o1");
});
