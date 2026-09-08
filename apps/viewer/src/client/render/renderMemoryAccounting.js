// Byte attribution of what the viewer retains for the displayed model, read by
// the headless memory harness through window.__cadRenderMemoryProbe(). Every
// GPU-side array is counted once (occurrences share component geometry), split
// into surface geometry, CAD edge lines and raycast BVHs, beside the render
// asset caches' own accounting. Pure over a runtime's display records.
import { renderAssetCacheStats } from "cadgen-js/lib/renderAssetClient.js";
import { cadEdgeInstanceSets } from "cadgen-js/common/cadEdgeInstances.js";

function geometryBuffers(geometry) {
  const buffers = new Set();
  if (geometry?.index) {
    buffers.add(geometry.index);
  }
  for (const attribute of Object.values(geometry?.attributes || {})) {
    buffers.add(attribute.isInterleavedBufferAttribute ? attribute.data : attribute);
  }
  return buffers;
}

function bvhBytes(geometry) {
  const roots = geometry?.boundsTree?._roots;
  if (!Array.isArray(roots)) {
    return 0;
  }
  return roots.reduce((sum, root) => sum + (root?.byteLength || 0), 0);
}

export function renderMemoryAccounting(runtime) {
  const records = Array.isArray(runtime?.displayRecords) ? runtime.displayRecords : [];
  const seenGeometries = new Set();
  const seenBuffers = new Set();
  const seenMaterials = new Set();
  const totals = {
    occurrences: 0,
    edgeObjects: 0,
    edgeInstanceSets: 0,
    edgeInstances: 0,
    geometries: 0,
    buffers: 0,
    materials: 0,
    surfaceBytes: 0,
    edgeBytes: 0,
    bvhBytes: 0,
    bvhGeometries: 0
  };
  const visit = (object, kind) => {
    const geometry = object?.geometry;
    if (!geometry) {
      return;
    }
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      if (material) {
        seenMaterials.add(material);
      }
    }
    if (seenGeometries.has(geometry)) {
      return;
    }
    seenGeometries.add(geometry);
    for (const buffer of geometryBuffers(geometry)) {
      if (seenBuffers.has(buffer)) {
        continue;
      }
      seenBuffers.add(buffer);
      totals[kind === "edge" ? "edgeBytes" : "surfaceBytes"] += buffer.array?.byteLength || 0;
    }
    const bvh = bvhBytes(geometry);
    if (bvh) {
      totals.bvhBytes += bvh;
      totals.bvhGeometries += 1;
    }
  };
  for (const record of records) {
    if (record?.mesh) {
      totals.occurrences += 1;
      visit(record.mesh, "surface");
    }
    if (record?.edges) {
      totals.edgeObjects += 1;
      record.edges.traverse ? record.edges.traverse((child) => visit(child, "edge")) : visit(record.edges, "edge");
    }
    if (record?.edgeInstance) {
      totals.edgeInstances += 1;
    }
  }
  // Instanced CAD edges: one draw per component; its segment texture (shared
  // by every occurrence, cached on the component), instance texture and quad.
  const seenSegmentTextures = new Set();
  for (const set of cadEdgeInstanceSets(runtime)) {
    totals.edgeInstanceSets += 1;
    visit(set.object, "edge");
    for (const material of set.materials) {
      seenMaterials.add(material);
    }
    totals.edgeBytes += set.instanceByteLength;
    if (!seenSegmentTextures.has(set.segments)) {
      seenSegmentTextures.add(set.segments);
      totals.edgeBytes += set.segments.byteLength;
    }
  }
  totals.geometries = seenGeometries.size;
  totals.buffers = seenBuffers.size;
  totals.materials = seenMaterials.size;
  return {
    ...totals,
    assetCaches: renderAssetCacheStats(),
    at: typeof performance !== "undefined" ? performance.now() : Date.now()
  };
}
