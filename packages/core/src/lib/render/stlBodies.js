// An STL's bodies: the connected pieces of its triangle soup, each a row of the view's Model tree and a part Select
// picks. Two triangles are one body where they share a vertex, vertices welded by position at a tolerance relative to the
// model's size (`STL_WELD_TOLERANCE` of its bounding box's diagonal: an STL repeats a shared corner bit for bit, so
// this only absorbs a writer's rounding). One pass over the vertices with a hash of their welded positions, union-find
// over the welds, one pass to number the bodies and one to put each body's triangles together: O(n), in the worker
// that parses the file (`stlMeshWorker.js`).
//
// An ASCII STL's named `solid` blocks stay apart (three's loader keeps them as groups): each is a row, split further only
// where it holds several bodies itself. Bodies are numbered largest first, by triangle count. Past `STL_BODY_LIMIT`
// bodies (a scan, a noisy mesh) the file is not split: one row, or one a solid.

/** The weld's tolerance, as a share of the model's bounding diagonal. */
export const STL_WELD_TOLERANCE = 1e-6;
/** The most bodies an STL is split into; past it, a row for the file (or for each named solid). */
export const STL_BODY_LIMIT = 2000;

// The vertices' bounding diagonal.
function diagonal(vertices) {
  let minX = Infinity, minY = Infinity, minZ = Infinity, maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (let at = 0; at < vertices.length; at += 3) {
    const x = vertices[at], y = vertices[at + 1], z = vertices[at + 2];
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
    if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
  }
  return Number.isFinite(minX) ? Math.hypot(maxX - minX, maxY - minY, maxZ - minZ) : 0;
}

/**
 * The bodies of the triangles from `first` to `first + count` (triangle soup: three vertices each, in order):
 * each triangle's body (0 for the largest, then by size) and each body's triangle count. Null past `limit` bodies.
 * @returns {{ body: Int32Array, sizes: number[] } | null}
 */
function bodiesOf(vertices, first, count, scale, limit) {
  const vertexCount = count * 3, base = first * 9;
  let size = 1;
  while (size < vertexCount * 2) size <<= 1;
  const mask = size - 1;
  const table = new Int32Array(size).fill(-1);
  // Each vertex's weld (the first vertex at its welded position), and the welds' union-find parents.
  const parent = new Int32Array(vertexCount);
  const weld = new Int32Array(vertexCount);
  const key = new Int32Array(vertexCount * 3);
  for (let v = 0; v < vertexCount; v += 1) {
    const at = base + v * 3;
    const qx = Math.round(vertices[at] * scale) | 0, qy = Math.round(vertices[at + 1] * scale) | 0, qz = Math.round(vertices[at + 2] * scale) | 0;
    key[v * 3] = qx; key[v * 3 + 1] = qy; key[v * 3 + 2] = qz;
    let slot = (Math.imul(qx, 73856093) ^ Math.imul(qy, 19349663) ^ Math.imul(qz, 83492791)) & mask;
    for (;;) {
      const held = table[slot];
      if (held < 0) { table[slot] = v; weld[v] = v; parent[v] = v; break; }
      if (key[held * 3] === qx && key[held * 3 + 1] === qy && key[held * 3 + 2] === qz) { weld[v] = held; break; }
      slot = (slot + 1) & mask;
    }
  }
  const find = node => {
    let root = node;
    while (parent[root] !== root) root = parent[root];
    while (parent[node] !== root) { const next = parent[node]; parent[node] = root; node = next; }
    return root;
  };
  const join = (a, b) => { a = find(a); b = find(b); if (a !== b) { if (a < b) parent[b] = a; else parent[a] = b; } };
  for (let t = 0; t < count; t += 1) {
    const w = weld[t * 3];
    join(w, weld[t * 3 + 1]);
    join(w, weld[t * 3 + 2]);
  }
  // Number the bodies as they first appear, count them, then renumber by size.
  const number = table; // reused: a root's body number (the table's length is at least the vertices').
  number.fill(-1);
  const body = new Int32Array(count);
  const counts = [];
  for (let t = 0; t < count; t += 1) {
    const root = find(weld[t * 3]);
    let id = number[root];
    if (id < 0) {
      if (counts.length >= limit) return null;
      id = number[root] = counts.length;
      counts.push(0);
    }
    body[t] = id;
    counts[id] += 1;
  }
  const bySize = counts.map((_, id) => id).sort((a, b) => counts[b] - counts[a] || a - b);
  const rank = new Int32Array(counts.length);
  bySize.forEach((id, place) => { rank[id] = place; });
  for (let t = 0; t < count; t += 1) body[t] = rank[body[t]];
  return { body, sizes: bySize.map(id => counts[id]) };
}

/**
 * The STL's bodies, as rows: `meshData`'s triangles put in body order (largest first; a named solid's together), with
 * `parts` naming each (`name`, its range, `body`: its number, from 1). One body: its solid's name, else "" (the view
 * names it for the file). Several: "Body 1"…, a named solid's "<solid> Body 1"….
 * @param {{ vertices: Float32Array, normals: Float32Array, indices: Uint32Array }} meshData  Triangle soup, indices in order.
 * @param {{ start: number, count: number, name: string }[]} [solids]  An ASCII STL's `solid` blocks (vertex ranges).
 * @returns {object}  `meshData` with its arrays reordered and `parts` set.
 */
export function withStlBodies(meshData, solids = []) {
  const { vertices, normals } = meshData;
  const triangles = Math.floor(vertices.length / 9);
  if (!triangles) return meshData;
  const span = diagonal(vertices);
  const scale = span > 0 ? 1 / (span * STL_WELD_TOLERANCE) : 1;
  const named = solids.length > 1 && solids.some(solid => solid.name);
  const blocks = named
    ? solids.map(solid => ({ first: Math.floor(solid.start / 3), count: Math.floor(solid.count / 3), name: String(solid.name || "").trim() }))
    : [{ first: 0, count: triangles, name: String(solids[0]?.name || "").trim() }];
  let found = blocks.map(block => bodiesOf(vertices, block.first, block.count, scale, STL_BODY_LIMIT));
  const total = found.reduce((sum, bodies) => sum + (bodies ? bodies.sizes.length : 1), 0);
  if (total > STL_BODY_LIMIT || found.some(bodies => !bodies)) found = blocks.map(() => null);
  // Each block's bodies in turn, largest first: a triangle's new place.
  const parts = [];
  const order = new Uint32Array(triangles);
  let next = 0;
  blocks.forEach((block, index) => {
    const bodies = found[index];
    const sizes = bodies ? bodies.sizes : [block.count];
    const starts = [];
    for (const size of sizes) {
      const name = sizes.length === 1 ? block.name || (named ? `Solid ${index + 1}` : "") : `${block.name ? `${block.name} ` : ""}Body ${starts.length + 1}`;
      parts.push({ name, vertexOffset: next * 3, vertexCount: size * 3, triangleOffset: next, triangleCount: size, body: parts.length + 1 });
      starts.push(next);
      next += size;
    }
    for (let t = 0; t < block.count; t += 1) order[starts[bodies ? bodies.body[t] : 0]++] = block.first + t;
  });
  // Already in order (one body, or bodies that were): nothing to move.
  let moved = false;
  for (let t = 0; t < triangles && !moved; t += 1) moved = order[t] !== t;
  if (!moved) return { ...meshData, parts };
  const place = (source) => {
    if (!source || source.length !== vertices.length) return source;
    const target = new Float32Array(source.length);
    for (let t = 0, to = 0; t < triangles; t += 1) {
      for (let from = order[t] * 9, end = from + 9; from < end; from += 1, to += 1) target[to] = source[from];
    }
    return target;
  };
  return { ...meshData, vertices: place(vertices), normals: place(normals), parts };
}
