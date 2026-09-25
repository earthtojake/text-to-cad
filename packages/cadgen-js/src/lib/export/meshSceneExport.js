// Shared final serialization for millimetre, Z-up triangle scenes. The CAD
// package exporter and already-tessellated organic meshes enter here after
// their different geometry preparation steps.
import { meshToBinaryStl } from "./meshFormats.js";
import { writeGlb } from "../glb/writeGlb.js";

export function meshSceneToStl({ primitives }, { name = "model" } = {}) {
  let total = 0;
  for (const primitive of primitives) total += primitive.positions.length;
  const positions = new Float32Array(total);
  let offset = 0;
  for (const primitive of primitives) {
    positions.set(primitive.positions, offset);
    offset += primitive.positions.length;
  }
  return meshToBinaryStl({ positions }, { name });
}

// glTF is Y-up metres; authoring meshes and STL are Z-up millimetres.
function yUpPrimitives(primitives) {
  return primitives.map((primitive) => {
    const rotate = (src, scale) => {
      const out = new Float32Array(src.length);
      for (let i = 0; i < src.length; i += 3) {
        out[i] = src[i] * scale;
        out[i + 1] = src[i + 2] * scale;
        out[i + 2] = -src[i + 1] * scale;
      }
      return out;
    };
    return {
      ...primitive,
      positions: rotate(primitive.positions, 0.001),
      normals: rotate(primitive.normals, 1),
    };
  });
}

export function meshSceneToGlb({ primitives }, {
  name = "model",
  sourceKind = "step",
  materialOptions,
  coordinates = "cad-mm-z-up",
  animations = null,
  nodeTransforms = null,
} = {}) {
  if (coordinates !== "cad-mm-z-up" && coordinates !== "gltf-m-y-up") {
    throw new Error("meshSceneToGlb: unsupported coordinate space");
  }
  const prepared = coordinates === "cad-mm-z-up" ? yUpPrimitives(primitives) : primitives;
  return writeGlb(
    { primitives: prepared },
    {
      preset: "export", name, sourceKind, units: "m", upAxis: "y",
      ...(materialOptions !== undefined ? { materialOptions } : {}),
      ...(animations ? { animations, nodeTransforms } : {}),
    },
  );
}
