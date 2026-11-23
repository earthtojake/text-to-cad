import { displayGeometryWithNormals } from "./meshNormals.js";
import { withStlBodies } from "./stlBodies.js";

function buildBoundsFromGeometry(geometry) {
  geometry.computeBoundingBox();
  const min = geometry.boundingBox?.min;
  const max = geometry.boundingBox?.max;
  if (!min || !max) {
    return {
      min: [0, 0, 0],
      max: [0, 0, 0],
    };
  }
  return {
    min: [min.x, min.y, min.z],
    max: [max.x, max.y, max.z],
  };
}

function buildDisplayGeometryFromStlGeometry(geometry, toCreasedNormals) {
  const displayGeometry = geometry.clone();
  // An STL's own normals are per facet; the display wants them smoothed or creased.
  displayGeometry.deleteAttribute?.("normal");
  const normalGeometry = displayGeometryWithNormals(displayGeometry, toCreasedNormals);
  if (normalGeometry !== displayGeometry) {
    displayGeometry.dispose?.();
  }
  return normalGeometry;
}

function buildGeometryIndices(geometry, vertexCount) {
  const indexAttribute = geometry.getIndex?.();
  if (indexAttribute?.count > 0) {
    return new Uint32Array(indexAttribute.array);
  }
  const indices = new Uint32Array(vertexCount);
  for (let index = 0; index < vertexCount; index += 1) {
    indices[index] = index;
  }
  return indices;
}

/**
 * An STL's mesh data: its triangles, display normals and bounds, one mesh (its `solid` blocks kept as `stlSolids`).
 * `bodies`: split into its bodies at once, a part each (`stlBodies.js`); the viewer splits them after the model shows
 * (`loadStlBodies`).
 */
export function buildMeshDataFromStlGeometry(geometry, { toCreasedNormals, bodies = false } = {}) {
  const displayGeometry = buildDisplayGeometryFromStlGeometry(geometry, toCreasedNormals);
  const positions = geometry.getAttribute("position");
  const displayPositions = displayGeometry.getAttribute("position");
  const displayNormals = displayGeometry.getAttribute("normal");
  try {
    if (!positions || positions.itemSize !== 3 || !displayPositions || displayPositions.itemSize !== 3) {
      throw new Error("STL geometry is missing vertex positions");
    }
    const vertexCount = displayPositions.count;
    const names = geometry.userData?.groupNames || [];
    const solids = (geometry.groups || []).map((group, index) => ({ start: group.start, count: group.count, name: String(names[index] || "").trim() }));
    const meshData = {
      vertices: new Float32Array(displayPositions.array),
      indices: buildGeometryIndices(displayGeometry, vertexCount),
      normals: displayNormals?.itemSize === 3 ? new Float32Array(displayNormals.array) : new Float32Array(displayPositions.array.length),
      colors: new Float32Array(0),
      edge_indices: new Uint32Array(0),
      bounds: buildBoundsFromGeometry(geometry),
      parts: [],
      has_source_colors: false,
      sourceColor: "",
      // An ASCII STL's `solid` blocks, as three's loader keeps them: a group each, in vertices, with its name; what
      // its bodies are split by (`stlBodies.js`). One named solid names the mesh.
      stlSolids: solids,
      name: solids.length === 1 ? solids[0].name : "",
    };
    return bodies ? withStlBodies(meshData, solids) : meshData;
  } finally {
    displayGeometry.dispose?.();
  }
}

// A binary STL is an 80-byte header, a count of facets, then 50 bytes a facet.
const STL_HEADER_BYTES = 84;
const STL_FACET_BYTES = 50;
// As far into a file as its text is looked for: a byte order mark and some blank lines.
const STL_TEXT_PROBE_BYTES = 1024;
// The sizes a real model's corners span, in any unit: up to a thousand kilometres in micrometres,
// and out to at least a nanometre in metres.
const STL_LARGEST_COORDINATE = 1e12;
const STL_SMALLEST_EXTENT = 1e-9;
// A character text has and numbers spell only by chance: a control character other than blank
// space, or a code point that is private or unassigned.
const NOT_TEXT = /[\0-\x08\x0e-\x1f\x7f-\x9f\p{Co}\p{Cn}]/u;

const count = value => value.toLocaleString("en-US");

function startsWithSolid(bytes, offset) {
  return offset + 5 <= bytes.length && String.fromCharCode(...bytes.subarray(offset, offset + 5)) === "solid";
}

// Where an STL's text begins when blank space (or a byte order mark) comes before it, else -1.
function stlTextStart(bytes) {
  let offset = bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf ? 3 : 0;
  const end = Math.min(bytes.length, STL_TEXT_PROBE_BYTES);
  while (offset < end && (bytes[offset] === 0x20 || (bytes[offset] >= 0x09 && bytes[offset] <= 0x0d))) offset += 1;
  return startsWithSolid(bytes, offset) ? offset : -1;
}

// Whether a file opens with text: UTF-8, or UTF-16 by its byte order mark or, without one, by a zero
// byte in every other place (UTF-16 text in Latin letters has one beside each). A binary STL never
// does past its header: its count and its facets' numbers hold zero bytes and control characters.
function opensWithText(bytes) {
  const probe = bytes.subarray(0, STL_TEXT_PROBE_BYTES);
  const everyOther = first => probe.length >= 2 && probe.every((byte, index) => index % 2 !== first || byte === 0);
  const encoding = (probe[0] === 0xff && probe[1] === 0xfe) || everyOther(1) ? "utf-16le"
    : (probe[0] === 0xfe && probe[1] === 0xff) || everyOther(0) ? "utf-16be"
    : "utf-8";
  try {
    return probe.length > 0 && !NOT_TEXT.test(new TextDecoder(encoding, { fatal: true }).decode(probe, { stream: true }));
  } catch {
    return false;
  }
}

// Whether the corners of the first `facets` facets are a model's: finite, none larger than a model's
// coordinate, and not all of them specks. Bytes that are not an STL's (an archive, an image) spell
// numbers of every size, soon one that is not finite; UTF-16 text spells nothing but specks.
function cornersArePlausible(view, facets) {
  let extent = 0;
  for (let facet = 0; facet < facets; facet += 1) {
    // A facet's normal is not looked at: exporters write a NaN one for a facet of no area.
    for (let offset = 12; offset < 48; offset += 4) {
      const size = Math.abs(view.getFloat32(STL_HEADER_BYTES + facet * STL_FACET_BYTES + offset, true));
      if (!(size <= STL_LARGEST_COORDINATE)) return false;
      extent = Math.max(extent, size);
    }
  }
  return extent >= STL_SMALLEST_EXTENT;
}

/**
 * The bytes three's STLLoader can read, or an error that says what is wrong with the file.
 *
 * STLLoader reads a file as binary unless "solid" is in its first few bytes, and takes the
 * facet count a binary file states on trust: it allocates for that many facets before it reads
 * one. So a file that is cut short, or is text that does not begin with "solid", or is no STL
 * at all, failed with whatever the browser says of the allocation or of the read past the end
 * ("invalid array length", "Array buffer allocation failed", "Offset is outside the bounds of
 * the DataView"), which names nothing a person can act on.
 *
 * A file whose count fits its size is handed over as it is, trailing bytes and all. One that
 * cannot be binary is text when "solid" follows blank space, and is read from there.
 *
 * A binary STL whose count is more than its size holds (a download cut short, or an exporter's
 * count too high) has the whole facets it holds read, as cad's STL reader reads them: a copy
 * states that many, and a partial last facet is left out. That is done only for a file that is
 * plausibly a binary STL, since the "count" of one that is not is whatever its bytes spell, and
 * its "facets" would be drawn as garbage: it holds a whole facet, it does not open with text, and
 * its corners are finite, none beyond a model's size and not all specks. Text is refused as text
 * that does not start with "solid"; anything else, with the count its header states.
 */
export function readableStlBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  // STLLoader's own test for text: "solid" within a byte order mark's length of the start.
  let loaderReadsText = false;
  for (let offset = 0; offset < 5; offset += 1) loaderReadsText ||= startsWithSolid(bytes, offset);
  const text = loaderReadsText ? 0 : stlTextStart(bytes);
  const notSolidText = `This is not an STL file: it is text that does not start with "solid", `
    + `and an STL in text form starts with that word.`;
  // STLLoader reads the count at byte 80 before it looks for text, so a shorter file fails there.
  if (bytes.length < STL_HEADER_BYTES) {
    if (text < 0 && opensWithText(bytes)) throw new Error(notSolidText);
    throw new Error(text >= 0
      ? `This STL file holds no triangles: it is ${count(bytes.length)} bytes.`
      : `This is not an STL file: it is ${count(bytes.length)} bytes, and a binary STL is at least ${STL_HEADER_BYTES}.`);
  }
  if (loaderReadsText) return buffer;
  const view = new DataView(buffer);
  const facets = view.getUint32(80, true);
  const stated = STL_HEADER_BYTES + facets * STL_FACET_BYTES;
  if (stated <= bytes.length) return buffer;
  if (text >= 0) return buffer.slice(text);
  if (opensWithText(bytes)) throw new Error(notSolidText);
  const whole = Math.floor((bytes.length - STL_HEADER_BYTES) / STL_FACET_BYTES);
  if (whole > 0 && cornersArePlausible(view, whole)) {
    const held = buffer.slice(0, STL_HEADER_BYTES + whole * STL_FACET_BYTES);
    new DataView(held).setUint32(80, whole, true);
    return held;
  }
  throw new Error(
    `This is not a complete STL file: its header counts ${count(facets)} triangles (${count(stated)} bytes), `
    + `and the file is ${count(bytes.length)} bytes. It may be cut short, or be another kind of file named .stl.`
  );
}

export async function buildMeshDataFromStlBuffer(buffer, { bodies = false } = {}) {
  const [{ STLLoader }, { toCreasedNormals }] = await Promise.all([
    import("three/examples/jsm/loaders/STLLoader.js"),
    import("three/examples/jsm/utils/BufferGeometryUtils.js"),
  ]);
  const loader = new STLLoader();
  const geometry = loader.parse(readableStlBuffer(buffer));
  try {
    return buildMeshDataFromStlGeometry(geometry, { toCreasedNormals, bodies });
  } finally {
    geometry.dispose?.();
  }
}
