import { readFileSync } from "node:fs";

// cadgen's tube skins for a 20 mm cord that its clip `curl` bends into a quarter
// circle of radius 40/pi mm about (0, 40/pi, 0) over one second, joints 2 mm
// apart, and the sidecar animation they bind: both written by cadgen
// (`make_fixture.py`), so the suites read what cadgen serves.
export const CURL_RADIUS = 40 / Math.PI;
export const CORD_RADIUS = 0.8;

export function tubeSkinsFixture() {
  const bytes = readFileSync(new URL("../fixtures/tube_skins/cord.skins.glb", import.meta.url));
  return {
    animation: JSON.parse(readFileSync(new URL("../fixtures/tube_skins/cord.animation.json", import.meta.url), "utf8")),
    buffer: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  };
}

/** How far each point (xyz, document space) sits from the axis of the circle the cord's
 * centerline is bent into when `angle` (radians) of it is curled: the cord's radius,
 * for a point on its wall. */
export function distanceFromCurl(points, angle = Math.PI / 2) {
  const radius = 20 / angle;
  const out = [];
  for (let point = 0; point < points.length; point += 3) {
    const [x, y, z] = [points[point], points[point + 1], points[point + 2]];
    out.push(Math.hypot(Math.hypot(x, y - radius) - radius, z));
  }
  return out;
}

const QUARTER_TURN_Z = [0, 0, Math.SQRT1_2, Math.SQRT1_2];

/**
 * A tube track over the scene tests' unit quad (`surfComponentMeshData`), already
 * given its skin, in the form a load leaves it: two joints along +X, 1 mm apart at
 * rest, and one key that stands the quad at z = 2 turned a quarter about +Z.
 */
export function quadTubeTrack(attachTubeSkins, edgeClasses, sourceMesh, occurrenceId) {
  const edgePositions = [];
  const edgeAlong = [];
  const ordinals = [];
  const classes = [];
  const clamp = (x) => Math.min(Math.max(x, 0), 1);
  for (const range of sourceMesh.cadEdgeClassRanges) {
    for (let segment = range.segmentStart; segment < range.segmentStart + range.segmentCount; segment += 1) {
      for (const end of [0, 1]) {
        const point = sourceMesh.cadEdgeIndices[segment * 2 + end] * 3;
        edgePositions.push(...sourceMesh.cadEdgePositions.slice(point, point + 3));
        edgeAlong.push(clamp(sourceMesh.cadEdgePositions[point]));
      }
      ordinals.push(segment + 1);
      classes.push(edgeClasses.indexOf(range.classId));
    }
  }
  const vertices = sourceMesh.vertices;
  const binding = {
    occurrence: occurrenceId,
    joints: 2,
    rest: new Float32Array([0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1]),
    positions: vertices.slice(),
    normals: sourceMesh.normals.slice(),
    indices: sourceMesh.indices.slice(),
    sourceTriangles: Uint32Array.from({ length: sourceMesh.indices.length / 3 }, (_, index) => index),
    along: Float32Array.from({ length: vertices.length / 3 }, (_, index) => clamp(vertices[index * 3])),
    material: new Float32Array(vertices.length),
    edgePositions: Float32Array.from(edgePositions),
    edgeAlong: Float32Array.from(edgeAlong),
    edgeOrdinals: Uint32Array.from(ordinals),
    edgeClasses: Uint8Array.from(classes)
  };
  const line = (start, end) => ({ normal: [0, 0, 1], segments: [{ kind: "line", start, end }] });
  const clips = { bend: { id: "bend", tracks: [{
    targets: [occurrenceId], times: [0], rest: line([0, 0, 0], [1, 0, 0]), maxSegmentLength: 1000,
    tube: [{ path: line([0, 0, 2], [0, 1, 2]), twistDeg: 0 }]
  }] } };
  const keys = new Float32Array([0, 0, 2, ...QUARTER_TURN_Z, 0, 1, 2, ...QUARTER_TURN_Z]);
  attachTubeSkins(clips, { bindings: [binding], tracks: [{ clip: "bend", track: 0, keys, bindings: [0] }] });
  return clips.bend.tracks[0];
}
