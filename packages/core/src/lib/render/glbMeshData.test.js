import assert from "node:assert/strict";
import { test } from "node:test";

import { buildMeshDataFromGlbBuffer, buildGlbDocumentFromBuffer } from "./glbMeshData.js";
import { createGlbScene } from "./glbScene.js";
import * as THREE from "three";

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
  nodeName = "leaf",
  upAxis = null,
  materialBaseColor = null,
  materialExtras = null,
  materialPbr = null,
  materialExtensions = null,
  duplicateMesh = false,
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
    ...(materialExtensions ? { extensionsUsed: Object.keys(materialExtensions) } : {}),
    scenes: [
      {
        nodes: [0]
      }
    ],
    nodes: [
      {
        name: nodeName,
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
                baseColorFactor: materialBaseColor,
                ...materialPbr
              },
              ...(materialExtensions ? { extensions: materialExtensions } : {}),
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
  if (duplicateMesh) {
    gltf.nodes.push({ ...gltf.nodes[0], name: "shared-material-copy" });
    gltf.scenes[0].nodes.push(1);
  }
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

test("authored GLB names remain separate from stable occurrence identity", async () => {
  const named = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({ nodeName: "left cylinder" }));
  assert.equal(named.parts[0].id, "o1.2");
  assert.equal(named.parts[0].occurrenceId, "o1.2");
  assert.equal(named.parts[0].name, "left cylinder");
  assert.equal(named.parts[0].label, "left cylinder");
  assert.equal(named.parts[0].vertexCount, 3);
  assert.equal(named.parts[0].triangleCount, 1);

  const unnamed = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({ nodeName: "" }));
  assert.equal(unnamed.parts[0].name, "o1.2", "a generated Three mesh name must not become an authored component");
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
  // A writer that pre-rotates its positions gets them back unchanged; correcting again
  // would stand the model on its edge. Only the declaration distinguishes it from the
  // file above.
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({ upAxis: "z" }));
  assert.deepEqual(cadVertices(meshData), Y_UP_UNCONVERTED);
});

test("GLB mesh data preserves neutral source material colors", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeTwoPrimitiveOccurrenceGlb({
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

test("GLB mesh data honors explicit non-source material metadata", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    materialBaseColor: [0.05, 0.05, 0.05, 1],
    materialExtras: { cadSourceColor: false }
  }));

  assert.equal(meshData.has_source_colors, false);
  assert.equal(meshData.sourceColor, "");
  assert.equal(meshData.parts[0].color, "");
  assert.equal(meshData.parts[0].hasSourceColors, false);
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

test("GLB mesh data preserves loaded material metadata on single-primitive meshes", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeIndexedMaterialOccurrenceGlb());

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.sourceColor, "#ff0000");
  assert.equal(meshData.parts[0].color, "#ff0000");
  assert.equal(meshData.parts[0].hasSourceColors, true);
});

test("GLB mesh data preserves material colors", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    materialBaseColor: [1, 0, 0, 1]
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.sourceColor, "#ff0000");
  assert.equal(meshData.colors.length, 0);
  assert.equal(meshData.parts[0].color, "#ff0000");
  assert.equal(meshData.parts[0].hasSourceColors, true);
});

test("GLB mesh data preserves source material opacity", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeOccurrenceGlb({
    materialBaseColor: [1, 0, 0, 0.2]
  }));

  assert.equal(meshData.has_source_colors, true);
  assert.equal(meshData.parts[0].color, "#ff0000");
  assert.equal(meshData.parts[0].opacity, 0.2);
  assert.equal(meshData.parts[0].hasSourceColors, true);
});

test("GLB mesh data assigns stable primitive indexes per occurrence", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(makeTwoPrimitiveOccurrenceGlb());

  assert.equal(meshData.parts.length, 2);
  assert.deepEqual(meshData.parts.map((part) => part.occurrenceId), ["o1.2", "o1.2"]);
  assert.deepEqual(meshData.parts.map((part) => part.primitiveIndex), [0, 1]);
  assert.deepEqual(meshData.parts.map((part) => part.triangleCount), [1, 1]);
});

test('external glTF buffers use the resource provider and release temporary URLs', async t => {
  const revoke = t.mock.method(URL, 'revokeObjectURL');
  const previous = globalThis.ProgressEvent;
  globalThis.ProgressEvent ||= class { constructor(type, values) { this.type=type; Object.assign(this,values); } };
  t.after(() => { globalThis.ProgressEvent=previous; });
  const positions = new Float32Array([0,0,0,1,0,0,0,1,0]);
  const source = new TextEncoder().encode(JSON.stringify({asset:{version:'2.0'},scene:0,
    scenes:[{nodes:[0]}],nodes:[{mesh:0}], meshes:[{primitives:[{attributes:{POSITION:0}}]}],
    buffers:[{uri:'private.bin',byteLength:positions.byteLength}],
    bufferViews:[{buffer:0,byteOffset:0,byteLength:positions.byteLength}],
    accessors:[{bufferView:0,componentType:5126,count:3,type:'VEC3',min:[0,0,0],max:[1,1,0]}],
  })).buffer;
  const calls = [];
  const resources = {
    resolveDependency: (source,reference) => {calls.push(['resolve',source,reference]);return 'private:bytes';},
    readBytes: async (url,options) => {calls.push(['read',url,options.maxBytes]);return positions.buffer;},
  };
  const mesh = await buildMeshDataFromGlbBuffer(source,{resources,sourceUrl:'private:document'});
  assert.equal(mesh.vertices.length, 9);
  assert.equal(revoke.mock.callCount(), 1);
  assert.deepEqual(calls,[['resolve','private:document','private.bin'],['read','private:bytes',64*1024*1024]]);
});

// Two triangles at a fold and no NORMAL attribute: glTF asks a client for flat normals, each
// triangle its own, kept outward under a mirroring placement (a negative determinant).
function twoTriangleGlb(scale = [1, 1, 1]) {
  const positions = floatBuffer([0, 0, 0, 0.001, 0, 0, 0, 0.001, 0, 0, 0, 0, 0, 0, 0.001, 0.001, 0, 0]);
  const binary = pad4(positions);
  const gltf = {
    asset: { version: "2.0" }, scenes: [{ nodes: [0] }], nodes: [{ name: "fold", mesh: 0, scale }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, mode: 4 }] }],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: positions.length, target: 34962 }],
    accessors: [{ bufferView: 0, componentType: 5126, count: 6, type: "VEC3", min: [0, 0, 0], max: [0.001, 0.001, 0.001] }]
  };
  const json = pad4(Buffer.from(JSON.stringify(gltf)), 0x20);
  const header = Buffer.alloc(12);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + json.length + 8 + binary.length, 8);
  const chunk = (data, type) => { const head = Buffer.alloc(8); head.writeUInt32LE(data.length, 0); head.writeUInt32LE(type, 4); return Buffer.concat([head, data]); };
  const glb = Buffer.concat([header, chunk(json, 0x4e4f534a), chunk(binary, 0x004e4942)]);
  return glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength);
}

test("a GLB primitive without normals is shaded flat, each triangle its own, mirrored or not", async () => {
  // glTF +Z and +Y, the two triangles' faces, are CAD -Y and +Z.
  const expected = [[0, -1, 0], [0, -1, 0], [0, -1, 0], [0, 0, 1], [0, 0, 1], [0, 0, 1]];
  for (const scale of [[1, 1, 1], [-1, 1, 1]]) {
    const meshData = await buildMeshDataFromGlbBuffer(twoTriangleGlb(scale));
    const normals = [];
    for (let at = 0; at < meshData.normals.length; at += 3) {
      normals.push(Array.from(meshData.normals.slice(at, at + 3), value => Math.round(value * 1e6) / 1e6 + 0));
    }
    assert.deepEqual(normals, expected, `scale ${scale}`);
  }
});


test("native GLB materials keep authored Standard and Physical finishes in edit and sibling views", async () => {
  for (const physical of [false, true]) {
    const buffer = makeOccurrenceGlb({ duplicateMesh: true, materialBaseColor: [0.2, 0.3, 0.4, 1],
      materialPbr: { metallicFactor: 1, roughnessFactor: 0.3 },
      materialExtensions: physical ? {
        KHR_materials_clearcoat: { clearcoatFactor: 1, clearcoatRoughnessFactor: 0.15 },
        KHR_materials_transmission: { transmissionFactor: 0.8 },
        KHR_materials_volume: { thicknessFactor: 0.006, attenuationDistance: 0.05, attenuationColor: [0.8, 0.9, 0.85] }
      } : null });
    const original = new Uint8Array(buffer).slice();
    const document = await buildGlbDocumentFromBuffer(buffer);
    const loadedMeshes = []; document.scene.traverse(object => { if (object.isMesh) loadedMeshes.push(object); });
    assert.equal(loadedMeshes.length, 2);
    assert.equal(loadedMeshes[0].material, loadedMeshes[1].material, "the loader shares the source material");
    const mesh = loadedMeshes[0], authored = mesh.material;
    if (physical) assert.equal(authored.attenuationDistance, 50, "a shared material is converted once, not once per mesh");
    assert.equal(authored.userData.cadAuthoredFinish, true);
    assert.equal(Boolean(authored.isMeshPhysicalMaterial), physical);
    const scene = createGlbScene(THREE, document);
    const look = { authored: false, surface: { style: "shaded", opacity: 1 },
      materialSettings: { defaultColor: "#b6c4ce", roughness: 0.58, metalness: 0.02, clearcoat: 0.12, envMapIntensity: 0 } };
    scene.setSurfaceLook(look);
    assert.equal(scene.keepsAuthoredFinish, true, "regular edit requests the existing neutral reflection environment");
    assert.deepEqual([mesh.material.metalness, mesh.material.roughness], [1, 0.3]);
    if (physical) assert.deepEqual([mesh.material.clearcoat, mesh.material.transmission, mesh.material.thickness, mesh.material.attenuationDistance], [1, 0.8, 0.006, 50]);
    for (let entry = 0; entry < 2; entry++) {
      const sibling = scene.createSibling();
      sibling.setSurfaceLook({ ...look, authored: true });
      let copy; sibling.object3D.traverse(object => { if (object.isMesh) copy = object; });
      assert.notEqual(copy.material, authored);
      assert.deepEqual([copy.material.metalness, copy.material.roughness], [1, 0.3]);
      if (physical) assert.deepEqual([copy.material.thickness, copy.material.attenuationDistance], [0.006, 50], "sibling creation never repeats the loader's world-unit conversion");
      sibling.dispose();
    }
    assert.deepEqual(new Uint8Array(buffer), original, "loading never rewrites the file bytes");
    if (physical) assert.equal(authored.attenuationDistance, 50);
    scene.dispose();
  }
  const document = await buildGlbDocumentFromBuffer(makeOccurrenceGlb());
  const scene = createGlbScene(THREE, document);
  assert.equal(scene.keepsAuthoredFinish, false, "GLTFLoader's implicit material retains the viewer fallback");
  scene.setSurfaceLook({ authored: false, surface: { style: "shaded", opacity: 1 }, materialSettings: { roughness: 0.58, metalness: 0.02 } });
  scene.object3D.traverse(object => { if (object.isMesh) assert.deepEqual([object.material.roughness, object.material.metalness], [0.58, 0.02]); });
  scene.dispose();
});
