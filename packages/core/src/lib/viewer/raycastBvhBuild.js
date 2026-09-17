import { BufferAttribute, BufferGeometry } from "three";
import { MeshBVH } from "three-mesh-bvh";

// Inputs belong to the worker. Never return the temporary geometry or its
// position/index buffers: the display retains its original arrays throughout.
export function buildSerializedRaycastBvh({ position, index, groups, drawRange }) {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(position, 3));
  if (index) geometry.setIndex(new BufferAttribute(index, 1));
  geometry.groups = groups;
  geometry.setDrawRange(drawRange.start, drawRange.count);
  const bvh = new MeshBVH(geometry, { indirect: true, setBoundingBox: false });
  const { version, roots, indirectBuffer } = MeshBVH.serialize(bvh, { cloneBuffers: false });
  return { version, roots, indirectBuffer };
}

export function raycastBvhResultTransfers(result) {
  return [...result.roots, result.indirectBuffer.buffer];
}
