// Turning one part of an assembly into STL bytes.
//
// The viewer hands out paths, not downloads: the same client runs in a browser,
// in the desktop shell and in an editor, and only the first of those can act on
// a download -- the desktop shell has no download handler at all, so a download
// button would silently do nothing there. So the bytes made here are POSTed and
// saved into the project, and the path comes back.
//
// Built from the mesh already on screen, so no kernel runs and nothing is
// generated: the server writes what it was handed.

/** Base64 for a byte buffer, in chunks so a large part does not blow the stack. */
export function encodeBase64(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = "";
  const CHUNK = 0x8000;
  for (let index = 0; index < bytes.length; index += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(index, index + CHUNK));
  }
  return btoa(binary);
}

/**
 * A group holding one clone per mesh, each carrying its source's WORLD
 * transform, ready for an exporter.
 *
 * `updateMatrixWorld` at the end is not optional: three's STLExporter reads
 * `object.matrixWorld` and never refreshes it, while `applyMatrix4` writes the
 * LOCAL matrix. Without it every part exports at the origin -- a file that
 * opens fine and has thrown away where the part sits in the assembly.
 */
export function buildExportGroup(THREE, meshes) {
  const group = new THREE.Group();
  for (const source of Array.isArray(meshes) ? meshes : []) {
    if (!source?.geometry) continue;
    source.updateWorldMatrix(true, false);
    const clone = new THREE.Mesh(source.geometry, source.material);
    clone.applyMatrix4(source.matrixWorld);
    group.add(clone);
  }
  group.updateMatrixWorld(true);
  return group;
}

/** Filesystem-friendly stem for a part, mirroring what the server will accept. */
export function exportNameForPart(partName, fallback = "part") {
  const stem = String(partName ?? "")
    .trim()
    .replace(/\.stl$/i, "")
    .replace(/[^\w.-]+/g, "_")
    .replace(/_{2,}/g, "_")
    .replace(/^[_.-]+|[_.-]+$/g, "");
  return `${stem || fallback}.stl`;
}
