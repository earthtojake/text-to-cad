import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildDisplayEdgeRuntime,
  buildSelectorRuntime,
  buildTransformedDisplayEdgeRuntime,
  buildTransformedSelectorRuntime
} from "./runtime.js";

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
  assert.equal(faces[1].copyText, "#o1.5.f2");
  assert.equal(faces[1].pickData.surfaceType, "plane");
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

test("buildSelectorRuntime uses STEP topology shape names in shape references", () => {
  const bundle = {
    manifest: {
      cadRef: "parts/labeled",
      tables: {
        occurrenceColumns: ["id", "path", "name", "sourceName", "parentId", "transform", "bbox", "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        shapeColumns: ["id", "occurrenceId", "ordinal", "kind", "name", "sourceName", "bbox", "center", "area", "volume", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        faceColumns: ["id", "occurrenceId", "shapeId", "ordinal", "surfaceType", "area", "center", "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags", "params", "triangleStart", "triangleCount"],
        edgeColumns: ["id", "occurrenceId", "shapeId", "ordinal", "curveType", "length", "center", "bbox", "faceStart", "faceCount", "relevance", "flags", "params", "segmentStart", "segmentCount"],
      },
      occurrences: [
        ["o1", "1", "base:front_left", "base", null, null, null, 0, 1, 0, 0, 0, 0]
      ],
      shapes: [
        ["o1.s1", "o1", 1, "solid", "base:front_left", "base", null, null, 24, 12, 0, 0, 0, 0]
      ],
      faces: [],
      edges: []
    },
    buffers: {}
  };

  const runtime = buildSelectorRuntime(bundle, { copyCadPath: "parts/labeled" });
  const shape = runtime.references.find((reference) => reference.selectorType === "shape");

  assert.equal(shape.summary, "base:front_left solid volume=12");
  assert.equal(shape.copyText, "#s1");
  assert.equal(shape.pickData.name, "base:front_left");
  assert.equal(shape.pickData.sourceName, "base");
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

test("buildTransformedSelectorRuntime applies part transforms to rows and proxy geometry", () => {
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
        ["o1", "1", null, null, null, null, { min: [0, 0, 0], max: [1, 1, 0] }, 0, 1, 0, 1, 0, 1]
      ],
      shapes: [
        ["o1.s1", "o1", 1, "solid", { min: [0, 0, 0], max: [1, 1, 0] }, [0.5, 0.5, 0], 1, 1, 0, 1, 0, 1]
      ],
      faces: [
        ["o1.f1", "o1", "o1.s1", 1, "plane", 1, [0.5, 0.5, 0], [0, 0, 1], { min: [0, 0, 0], max: [1, 1, 0] }, 0, 1, 0, 0, {}, 0, 1]
      ],
      edges: [
        ["o1.e1", "o1", "o1.s1", 1, "line", 1, [0.5, 0, 0], { min: [0, 0, 0], max: [1, 0, 0] }, 0, 1, 0, 0, {}, 0, 1]
      ],
      relations: {
        faceEdgeRows: [0],
        edgeFaceRows: [0]
      }
    },
    buffers: {
      facePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0
      ]),
      faceIndices: new Uint32Array([0, 1, 2]),
      faceIds: new Uint32Array([0]),
      edgePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0
      ]),
      edgeIndices: new Uint32Array([0, 1]),
      edgeIds: new Uint32Array([0])
    }
  };
  const runtime = buildSelectorRuntime(bundle);
  const transformed = buildTransformedSelectorRuntime(runtime, new Map([
    ["o1", [
      1, 0, 0, 10,
      0, 1, 0, 20,
      0, 0, 1, 30,
      0, 0, 0, 1
    ]]
  ]));

  assert.deepEqual(transformed.faces[0].center, [10.5, 20.5, 30]);
  assert.deepEqual(transformed.edges[0].center, [10.5, 20, 30]);
  assert.deepEqual(transformed.references.find((reference) => reference.selectorType === "face").pickData.center, [10.5, 20.5, 30]);
  assert.deepEqual(Array.from(transformed.proxy.facePositions), [
    10, 20, 30,
    11, 20, 30,
    10, 21, 30
  ]);
  assert.deepEqual(Array.from(transformed.proxy.faceIndices), [0, 1, 2]);
  assert.deepEqual(Array.from(transformed.proxy.faceIds), [0]);
  assert.deepEqual(Array.from(transformed.proxy.edgePositions), [
    10, 20, 30,
    11, 20, 30
  ]);
  assert.deepEqual(Array.from(transformed.proxy.edgeIndices), [0, 1]);
  assert.deepEqual(Array.from(transformed.proxy.edgeIds), [0]);
});

test("buildDisplayEdgeRuntime keeps compact edge rows without selector references", () => {
  const runtime = buildDisplayEdgeRuntime({
    manifest: {
      schemaVersion: 2,
      stepHash: "abc",
      bbox: { min: [0, 0, 0], max: [1, 0, 0] },
      tables: {
        edgeColumns: ["occurrenceId", "segmentStart", "segmentCount", "visibilityClass"]
      },
      edges: [["o1", 0, 1, "feature"]],
      edgeProxy: {
        positionsView: "edgePositions",
        indicesView: "edgeIndices",
        edgeIdsView: "edgeIds"
      }
    },
    buffers: {
      edgePositions: new Float32Array([0, 0, 0, 1, 0, 0]),
      edgeIndices: new Uint32Array([0, 1]),
      edgeIds: new Uint32Array([0])
    }
  });

  assert.equal(runtime.stepHash, "abc");
  assert.deepEqual(runtime.edges, [{ occurrenceId: "o1", segmentStart: 0, segmentCount: 1, visibilityClass: "feature" }]);
  assert.deepEqual(Array.from(runtime.proxy.edgeIndices), [0, 1]);
  assert.equal(runtime.referenceMap, undefined);
});

test("buildTransformedDisplayEdgeRuntime applies occurrence transforms to edge proxy geometry", () => {
  const runtime = buildDisplayEdgeRuntime({
    manifest: {
      schemaVersion: 2,
      tables: {
        edgeColumns: ["occurrenceId", "segmentStart", "segmentCount"]
      },
      edges: [["o1", 0, 1]],
      edgeProxy: {
        positionsView: "edgePositions",
        indicesView: "edgeIndices",
        edgeIdsView: "edgeIds"
      }
    },
    buffers: {
      edgePositions: new Float32Array([0, 0, 0, 1, 0, 0]),
      edgeIndices: new Uint32Array([0, 1]),
      edgeIds: new Uint32Array([0])
    }
  });
  const transformed = buildTransformedDisplayEdgeRuntime(runtime, new Map([
    ["o1", [
      1, 0, 0, 10,
      0, 1, 0, 20,
      0, 0, 1, 30,
      0, 0, 0, 1
    ]]
  ]));

  assert.deepEqual(Array.from(transformed.proxy.edgePositions), [
    10, 20, 30,
    11, 20, 30
  ]);
  assert.deepEqual(Array.from(transformed.proxy.edgeIndices), [0, 1]);
  assert.deepEqual(Array.from(transformed.proxy.edgeIds), [0]);
});
