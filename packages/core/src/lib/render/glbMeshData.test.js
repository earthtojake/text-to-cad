import assert from "node:assert/strict";
import { test } from "node:test";

import { buildMeshDataFromGlbBuffer } from "./glbMeshData.js";

function pad4(buffer, padByte = 0) {
  const padding = (4 - (buffer.length % 4)) % 4;
  return padding ? Buffer.concat([buffer, Buffer.alloc(padding, padByte)]) : buffer;
}

function floatBuffer(values) {
  const buffer = Buffer.alloc(values.length * 4);
  values.forEach((value, index) => buffer.writeFloatLE(value, index * 4));
  return buffer;
}

function uint32Buffer(values) {
  const buffer = Buffer.alloc(values.length * 4);
  values.forEach((value, index) => buffer.writeUInt32LE(value, index * 4));
  return buffer;
}

function makeOccurrenceGlb({
  cadExtras = true,
  upAxis = null,
  stepTopology = false,
  materialBaseColor = null,
  materialExtras = null,
  vertexColors = null
} = {}) {
  const positions = floatBuffer([
    0, 0, 0,
    0.001, 0, 0,
    0, 0.001, 0
  ]);
  const colors = Array.isArray(vertexColors) ? floatBuffer(vertexColors) : Buffer.alloc(0);
  const indices = uint32Buffer([0, 1, 2]);
  const binary = pad4(Buffer.concat([positions, colors, indices]));
  const primitive = {
    attributes: {
      POSITION: 0,
      ...(colors.length ? { COLOR_0: 2 } : {})
    },
    indices: 1,
    mode: 4,
    ...(Array.isArray(materialBaseColor) ? { material: 0 } : {})
  };
  const gltf = {
    asset: {
      version: "2.0"
    },
    ...(stepTopology
      ? {
          extensionsUsed: ["STEP_topology"],
          extensions: {
            STEP_topology: {}
          }
        }
      : {}),
    scenes: [
      {
        nodes: [0]
      }
    ],
    nodes: [
      {
        name: "leaf",
        mesh: 0,
        ...(cadExtras || upAxis
          ? {
              extras: {
                ...(cadExtras ? { cadOccurrenceId: "o1.2" } : {}),
                ...(upAxis ? { cadUpAxis: upAxis } : {})
              }
            }
          : {})
      }
    ],
    meshes: [
      {
        primitives: [primitive]
      }
    ],
    ...(Array.isArray(materialBaseColor)
      ? {
          materials: [
            {
              pbrMetallicRoughness: {
                baseColorFactor: materialBaseColor
              },
              ...(materialExtras ? { extras: materialExtras } : {})
            }
          ]
        }
      : {}),
    buffers: [
      {
        byteLength: binary.length
      }
    ],
    bufferViews: [
      {
        buffer: 0,
        byteOffset: 0,
        byteLength: positions.length,
        target: 34962
      },
      {
        buffer: 0,
        byteOffset: positions.length + colors.length,
        byteLength: indices.length,
        target: 34963
      },
      ...(colors.length
        ? [
            {
              buffer: 0,
              byteOffset: positions.length,
              byteLength: colors.length,
              target: 34962
            }
          ]
        : [])
    ],
    accessors: [
      {
        bufferView: 0,
        byteOffset: 0,
        componentType: 5126,
        count: 3,
        type: "VEC3",
        min: [0, 0, 0],
        max: [0.001, 0.001, 0]
      },
      {
        bufferView: 1,
        byteOffset: 0,
        componentType: 5125,
        count: 3,
        type: "SCALAR",
        min: [0],
        max: [2]
      },
      ...(colors.length
        ? [
            {
              bufferView: 2,
              byteOffset: 0,
              componentType: 5126,
              count: 3,
              type: "VEC3"
            }
          ]
        : [])
    ]
  };
  const json = pad4(Buffer.from(JSON.stringify(gltf), "utf8"), 0x20);
  const header = Buffer.alloc(12);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + json.length + 8 + binary.length, 8);
  const jsonHeader = Buffer.alloc(8);
  jsonHeader.writeUInt32LE(json.length, 0);
  jsonHeader.writeUInt32LE(0x4e4f534a, 4);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(binary.length, 0);
  binHeader.writeUInt32LE(0x004e4942, 4);
  const glb = Buffer.concat([header, jsonHeader, json, binHeader, binary]);
  return glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength);
}

function makeTwoPrimitiveOccurrenceGlb({
  stepTopology = false,
  materialBaseColors = [
    [1, 0, 0, 1],
    [0, 0, 1, 1]
  ],
  materialExtras = []
} = {}) {
  const positions = floatBuffer([
    0, 0, 0,
    0.001, 0, 0,
    0, 0.001, 0,
    0.002, 0, 0,
    0.003, 0, 0,
    0.002, 0.001, 0
  ]);
  const firstIndices = uint32Buffer([0, 1, 2]);
  const secondIndices = uint32Buffer([3, 4, 5]);
  const binary = pad4(Buffer.concat([positions, firstIndices, secondIndices]));
  const secondIndexOffset = positions.length + firstIndices.length;
  const gltf = {
    asset: {
      version: "2.0"
    },
    ...(stepTopology
      ? {
          extensionsUsed: ["STEP_topology"],
          extensions: {
            STEP_topology: {}
          }
        }
      : {}),
    scenes: [
      {
        nodes: [0]
      }
    ],
    nodes: [
      {
        name: "leaf",
        mesh: 0,
        extras: {
          cadOccurrenceId: "o1.2"
        }
      }
    ],
    meshes: [
      {
        primitives: [
          {
            attributes: {
              POSITION: 0
            },
            indices: 1,
            material: 0,
            mode: 4
          },
          {
            attributes: {
              POSITION: 0
            },
            indices: 2,
            material: 1,
            mode: 4
          }
        ]
      }
    ],
    materials: materialBaseColors.map((baseColorFactor, index) => ({
      pbrMetallicRoughness: {
        baseColorFactor
      },
      ...(materialExtras[index] ? { extras: materialExtras[index] } : {})
    })),
    buffers: [
      {
        byteLength: binary.length
      }
    ],
    bufferViews: [
      {
        buffer: 0,
        byteOffset: 0,
        byteLength: positions.length,
        target: 34962
      },
      {
        buffer: 0,
        byteOffset: positions.length,
        byteLength: firstIndices.length,
        target: 34963
      },
      {
        buffer: 0,
        byteOffset: secondIndexOffset,
        byteLength: secondIndices.length,
        target: 34963
      }
    ],
    accessors: [
      {
        bufferView: 0,
        byteOffset: 0,
        componentType: 5126,
        count: 6,
        type: "VEC3",
        min: [0, 0, 0],
        max: [0.003, 0.001, 0]
      },
      {
        bufferView: 1,
        byteOffset: 0,
        componentType: 5125,
        count: 3,
        type: "SCALAR",
        min: [0],
        max: [2]
      },
      {
        bufferView: 2,
        byteOffset: 0,
        componentType: 5125,
        count: 3,
        type: "SCALAR",
        min: [3],
        max: [5]
      }
    ]
  };
  const json = pad4(Buffer.from(JSON.stringify(gltf), "utf8"), 0x20);
  const header = Buffer.alloc(12);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + json.length + 8 + binary.length, 8);
  const jsonHeader = Buffer.alloc(8);
  jsonHeader.writeUInt32LE(json.length, 0);
  jsonHeader.writeUInt32LE(0x4e4f534a, 4);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(binary.length, 0);
  binHeader.writeUInt32LE(0x004e4942, 4);
  const glb = Buffer.concat([header, jsonHeader, json, binHeader, binary]);
  return glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength);
}

function makeIndexedMaterialOccurrenceGlb({
  stepTopology = false,
  primitiveMaterial = 1,
  materialBaseColors = [
    [0.72, 0.72, 0.72, 1],
    [1, 0, 0, 1]
  ],
  materialExtras = [
    { cadSourceColor: false },
    { cadSourceColor: true }
  ]
} = {}) {
  const positions = floatBuffer([
    0, 0, 0,
    0.001, 0, 0,
    0, 0.001, 0
  ]);
  const indices = uint32Buffer([0, 1, 2]);
  const binary = pad4(Buffer.concat([positions, indices]));
  const gltf = {
    asset: {
      version: "2.0"
    },
    ...(stepTopology
      ? {
          extensionsUsed: ["STEP_topology"],
          extensions: {
            STEP_topology: {}
          }
        }
      : {}),
    scenes: [
      {
        nodes: [0]
      }
    ],
    nodes: [
      {
        name: "leaf",
        mesh: 0,
        extras: {
          cadOccurrenceId: "o1.2"
        }
      }
    ],
    meshes: [
      {
        primitives: [
          {
            attributes: {
              POSITION: 0
            },
            indices: 1,
            material: primitiveMaterial,
            mode: 4
          }
        ]
      }
    ],
    materials: materialBaseColors.map((baseColorFactor, index) => ({
      pbrMetallicRoughness: {
        baseColorFactor
      },
      ...(materialExtras[index] ? { extras: materialExtras[index] } : {})
    })),
    buffers: [
      {
        byteLength: binary.length
      }
    ],
    bufferViews: [
      {
        buffer: 0,
        byteOffset: 0,
        byteLength: positions.length,
        target: 34962
      },
      {
        buffer: 0,
        byteOffset: positions.length,
        byteLength: indices.length,
        target: 34963
      }
    ],
    accessors: [
      {
        bufferView: 0,
        byteOffset: 0,
        componentType: 5126,
        count: 3,
        type: "VEC3",
        min: [0, 0, 0],
        max: [0.001, 0.001, 0]
      },
      {
        bufferView: 1,
        byteOffset: 0,
        componentType: 5125,
        count: 3,
        type: "SCALAR",
        min: [0],
        max: [2]
      }
    ]
  };
  const json = pad4(Buffer.from(JSON.stringify(gltf), "utf8"), 0x20);
  const header = Buffer.alloc(12);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + json.length + 8 + binary.length, 8);
  const jsonHeader = Buffer.alloc(8);
  jsonHeader.writeUInt32LE(json.length, 0);
  jsonHeader.writeUInt32LE(0x4e4f534a, 4);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(binary.length, 0);
  binHeader.writeUInt32LE(0x004e4942, 4);
  const glb = Buffer.concat([header, jsonHeader, json, binHeader, binary]);
  return glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength);
}

/** The fixture triangle is 1mm along +X and 1mm along glTF's +Y (out of the sheet). */
const Y_UP_UNCONVERTED = [
  0, 0, 0,
  1, 0, 0,
  0, 1, 0
];
/** The same triangle after the Y-up -> CAD Z-up correction: (x, y, z) -> (x, -z, y). */
const CONVERTED_TO_CAD = [
  0, 0, 0,
  1, 0, 0,
  0, 0, 1
];

function cadVertices(meshData) {
  return Array.from(meshData.vertices, (value) => (Object.is(value, -0) ? 0 : value));
}

test("GLB mesh data preserves cadOccurrenceId node extras", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb());

  assert.equal(meshData.parts.length, 1);
  assert.equal(meshData.parts[0].id, "o1.2");
  assert.equal(meshData.parts[0].occurrenceId, "o1.2");
  assert.equal(meshData.parts[0].primitiveIndex, 0);
  // An occurrence id is an identity NAMESPACE and says NOTHING about orientation. It was
  // once read as "already CAD space", which skipped the correction for every GLB cadgen
  // wrote (both presets stamp the id) and rendered them on their side.
  assert.deepEqual(cadVertices(meshData), CONVERTED_TO_CAD);
});

test("native GLB mesh data converts Y-up meters to CAD Z-up millimeters", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({ cadExtras: false }));

  assert.equal(meshData.parts.length, 1);
  assert.equal(meshData.parts[0].id, "glb:0");
  assert.equal(meshData.parts[0].label, "leaf");
  assert.deepEqual(cadVertices(meshData), CONVERTED_TO_CAD);
});

test("a GLB DECLARING glTF Y-up is converted, occurrence ids or not", async () => {
  // The regression: an inferred coordinate space. Both of these carry cadOccurrenceId,
  // which used to veto the correction; the declaration is what the reader must obey.
  const declared = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({ upAxis: "y" }));
  assert.deepEqual(cadVertices(declared), CONVERTED_TO_CAD);
  const declaredWithoutIds = await buildMeshDataFromGlbBuffer(
    makeOccurrenceGlb({ upAxis: "y", cadExtras: false })
  );
  assert.deepEqual(cadVertices(declaredWithoutIds), CONVERTED_TO_CAD);
});

test("a GLB DECLARING CAD Z-up is left alone", async () => {
  // bin/dxf-mesh.mjs pre-rotates its positions, so correcting again would stand the
  // drawing on its edge. Only the declaration distinguishes it from the file above.
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({ upAxis: "z" }));
  assert.deepEqual(cadVertices(meshData), Y_UP_UNCONVERTED);
});

test("STEP topology still means CAD space when nothing is declared", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(
    makeOccurrenceGlb({ stepTopology: true })
  );
  assert.deepEqual(cadVertices(meshData), Y_UP_UNCONVERTED);
});

test("STEP GLB mesh data ignores generated default material colors", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    stepTopology: true,
    materialBaseColor: [0.72, 0.72, 0.72, 1]
  }));

  assert.equal(meshData.has_source_colors, false);
  assert.equal(meshData.sourceColor, "");
  assert.deepEqual([...meshData.colors], []);
  assert.equal(meshData.parts[0].color, "");
  assert.equal(meshData.parts[0].hasSourceColors, false);
});

test("STEP GLB mesh data preserves neutral source material colors", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeTwoPrimitiveOccurrenceGlb({
    stepTopology: true,
    materialBaseColors: [
      [0, 0, 0, 1],
      [1, 1, 1, 1]
    ]
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.sourceColor, "");
  assert.deepEqual(meshData.parts.map((part) => part.color), ["#000000", "#ffffff"]);
  assert.deepEqual(meshData.parts.map((part) => part.hasSourceColors), [true, true]);
});

test("STEP GLB mesh data honors explicit non-source material metadata", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    stepTopology: true,
    materialBaseColor: [0.05, 0.05, 0.05, 1],
    materialExtras: { cadSourceColor: false }
  }));

  assert.equal(meshData.has_source_colors, false);
  assert.equal(meshData.sourceColor, "");
  assert.equal(meshData.parts[0].color, "");
  assert.equal(meshData.parts[0].hasSourceColors, false);
});

test("STEP GLB mesh data honors explicit source material metadata", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    stepTopology: true,
    materialBaseColor: [0.72, 0.72, 0.72, 1],
    materialExtras: { cadSourceColor: true }
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.sourceColor, "#dddddd");
  assert.equal(meshData.parts[0].color, "#dddddd");
  assert.equal(meshData.parts[0].hasSourceColors, true);
});

test("plain GLB COLOR_0 vertex colors are source colors", async () => {
  // No materials at all: the ramp must still survive as per-vertex source
  // colors instead of collapsing to the theme fill (the FEA-ramp regression).
  const ramp = [1, 0, 0, 0.5, 0, 0.5, 0, 0, 1];
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    cadExtras: false,
    vertexColors: ramp
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.parts[0].hasSourceColors, true);
  // No material declared a color, so the whole-mesh source color stays empty.
  assert.equal(meshData.parts[0].color, "");
  assert.equal(meshData.colors.length, meshData.vertices.length);
  assert.deepEqual([...meshData.colors], ramp);
});

test("a material color alongside COLOR_0 keeps vertex colors flowing", async () => {
  const ramp = [1, 0, 0, 0.5, 0, 0.5, 0, 0, 1];
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    cadExtras: false,
    vertexColors: ramp,
    materialBaseColor: [1, 1, 1, 1]
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.parts[0].hasSourceColors, true);
  assert.deepEqual([...meshData.colors], ramp);
});

test("STEP GLB mesh data preserves loaded material metadata on single-primitive meshes", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeIndexedMaterialOccurrenceGlb({
    stepTopology: true
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.sourceColor, "#ff0000");
  assert.equal(meshData.parts[0].color, "#ff0000");
  assert.equal(meshData.parts[0].hasSourceColors, true);
});

test("STEP GLB mesh data preserves non-gray material colors", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    stepTopology: true,
    materialBaseColor: [1, 0, 0, 1]
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.sourceColor, "#ff0000");
  assert.equal(meshData.colors.length, 0);
  assert.equal(meshData.parts[0].color, "#ff0000");
  assert.equal(meshData.parts[0].hasSourceColors, true);
});

test("STEP GLB mesh data preserves source material opacity", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    stepTopology: true,
    materialBaseColor: [1, 0, 0, 0.2]
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.parts[0].color, "#ff0000");
  assert.equal(meshData.parts[0].opacity, 0.2);
  assert.equal(meshData.parts[0].hasSourceColors, true);
});

test("STEP GLB mesh data preserves colored primitives alongside generated default materials", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeTwoPrimitiveOccurrenceGlb({
    stepTopology: true,
    materialBaseColors: [
      [0.72, 0.72, 0.72, 1],
      [0.05, 0.33, 0.86, 1]
    ]
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.sourceColor, "#3f9bef");
  assert.equal(meshData.colors.length, 0);
  assert.equal(meshData.parts[0].color, "");
  assert.equal(meshData.parts[0].hasSourceColors, false);
  assert.equal(meshData.parts[1].color, "#3f9bef");
  assert.equal(meshData.parts[1].hasSourceColors, true);
});

test("GLB mesh data assigns stable primitive indexes per occurrence", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeTwoPrimitiveOccurrenceGlb());

  assert.equal(meshData.parts.length, 2);
  assert.deepEqual(meshData.parts.map((part) => part.occurrenceId), ["o1.2", "o1.2"]);
  assert.deepEqual(meshData.parts.map((part) => part.primitiveIndex), [0, 1]);
  assert.deepEqual(meshData.parts.map((part) => part.triangleCount), [1, 1]);
});
