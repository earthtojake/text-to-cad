/**
 * A board in 3D, its parts: each footprint's 3D models where they stand (`partPlacement.js`), in the
 * models' authored colours, and a see-through block where a model is named and missing.
 *
 * A model is a STEP the engine served (`xbf/xbfDocument.js`'s `loadXbfDocument`: its structure and one
 * mesh per prototype), BAKED here into ONE geometry (every instance of the document placed, its faces
 * grouped by colour, a material each) shared by every placement of it: a board of 175 parts of 27
 * distinct models holds 27 geometries. The document's own buffers are let go once baked. A model is
 * known by its key (`document@stamp`, the board's models table's: a model file edited is a new key),
 * and released when no placement uses it any more.
 *
 * Placements are diffed by reference on every `setParts`: a part that did not change keeps its meshes, a
 * moved one is a matrix, and only a model never held is asked for (`wanted`).
 *
 * A model's own opacity (KiCad's per-model `opacity`, the payload's, absent at 1) scales its materials'
 * on that placement: below 1 they are see-through and write no depth.
 *
 * A hover is a pick a frame: each baked geometry gets its accelerator (`viewer/raycastBvh.js`, as the 3D
 * views' scenes do) in idle time, the first time a ray reaches its box.
 *
 * The highlight is the 3D views' (the overlay's colours, `board2d/boardOverlay.js`: selected, hovered);
 * while something is isolated the bodies that are not it fade. A block is the theme's muted ink, a
 * millimetre tall on the part's outline (its courtyard), see-through and edged: plainly no model.
 *
 * three.js is passed in. Importing this module has no environmental effects.
 */
import { boardOverlayColors } from "../board2d/boardOverlay.js";
import { BOARD_THICKNESS_MM } from "./boardFrame.js";
import { modelMatrix } from "./partPlacement.js";
import { loadXbfDocument, xbfDocumentSource } from "../xbf/xbfDocument.js";
import { scheduleRuntimeRaycastBvh } from "../viewer/raycastBvh.js";

// What stands for the engine's look (`xbfLook.js`) when a document is read for its triangles alone.
const NO_LOOK = Object.freeze({});

/** How tall a missing model's block stands, in millimetres. */
export const BLOCK_HEIGHT_MM = 1;
// What a faded body keeps of itself while something else is isolated.
const FADED_OPACITY = 0.15;
const SELECTED_BLEND = 0.55, HOVER_BLEND = 0.35;
const DEFAULT_SURFACE = [0.48, 0.5, 0.54, 1];
const BLOCK_INK = Object.freeze({ dark: { fill: 0x9aa3ad, edge: 0xc3cad2, opacity: 0.22 }, light: { fill: 0x6b7280, edge: 0x4b5563, opacity: 0.18 } });

const finite = (value, fallback) => (Number.isFinite(Number(value)) ? Number(value) : fallback);
// The area of a part's outline's box, in square millimetres: how big it stands on the board.
const outlineArea = part => {
  const ring = Array.isArray(part?.outline) ? part.outline : [];
  if (!ring.length) return 0;
  const xs = ring.map(point => finite(point?.[0], 0)), ys = ring.map(point => finite(point?.[1], 0));
  return (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys));
};
// A model's own opacity on its placement (the payload's `opacity`, KiCad's), 0 to 1; 1 where absent.
const opacityOf = model => Math.min(Math.max(finite(model?.opacity, 1), 0), 1);
const colorKey = rgba => (rgba ? rgba.map(value => Math.round(finite(value, 0) * 1000)).join(",") : "");

/**
 * One served model's document baked into one geometry in the model's frame: every instance placed by its
 * matrix, its triangles grouped by colour (a face's own, else its instance's, else its prototype's).
 * @param {typeof import("three")} THREE
 * @param {{ structure: { prototypes: object[], instances: object[] }, parts: Map<string, { mesh: object }> }} document
 * @returns {{ geometry: object, colors: (number[] | null)[], triangles: number, bytes: number }}
 */
export function bakeModel(THREE, document) {
  const { prototypes, instances } = document.structure;
  const pieces = [];
  let vertices = 0;
  for (const instance of instances) {
    const prototype = prototypes[instance.prototype];
    const part = prototype ? document.parts.get(String(prototype.key)) : null;
    if (!part?.mesh || !Array.isArray(instance.matrix) || instance.matrix.length !== 16) continue;
    pieces.push({ mesh: part.mesh, matrix: instance.matrix, rgba: instance.color || prototype.color || null, faceColors: prototype.faceColors || {}, first: vertices });
    vertices += part.mesh.positions.length / 3;
  }
  const positions = new Float32Array(vertices * 3), normals = new Float32Array(vertices * 3);
  const buckets = new Map();
  const bucket = rgba => {
    const key = colorKey(rgba);
    let found = buckets.get(key);
    if (!found) buckets.set(key, found = { rgba, indices: [] });
    return found;
  };
  const matrix = new THREE.Matrix4(), normalMatrix = new THREE.Matrix3(), point = new THREE.Vector3();
  for (const piece of pieces) {
    const { mesh } = piece;
    matrix.fromArray(piece.matrix);
    normalMatrix.getNormalMatrix(matrix);
    for (let at = 0, to = piece.first * 3; at < mesh.positions.length; at += 3, to += 3) {
      point.set(mesh.positions[at], mesh.positions[at + 1], mesh.positions[at + 2]).applyMatrix4(matrix);
      positions[to] = point.x; positions[to + 1] = point.y; positions[to + 2] = point.z;
      point.set(mesh.normals[at], mesh.normals[at + 1], mesh.normals[at + 2]).applyMatrix3(normalMatrix).normalize();
      normals[to] = point.x; normals[to + 1] = point.y; normals[to + 2] = point.z;
    }
    for (let row = 0; row < mesh.faces.length; row += 3) {
      const ordinal = String(mesh.faces[row]), first = mesh.faces[row + 1], count = mesh.faces[row + 2];
      const into = bucket(piece.faceColors[ordinal] || piece.rgba).indices;
      for (let at = first; at < first + count; at += 1) into.push(mesh.indices[at] + piece.first);
      // (`count` is the face's index count: 0 for a face the mesher left without triangles.)
    }
  }
  const index = new Uint32Array([...buckets.values()].reduce((sum, entry) => sum + entry.indices.length, 0));
  const geometry = new THREE.BufferGeometry();
  const colors = [];
  let start = 0;
  for (const entry of buckets.values()) {
    index.set(entry.indices, start);
    geometry.addGroup(start, entry.indices.length, colors.length);
    colors.push(entry.rgba);
    start += entry.indices.length;
  }
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
  geometry.setIndex(new THREE.BufferAttribute(index, 1));
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return { geometry, colors, triangles: index.length / 3, bytes: positions.byteLength + normals.byteLength + index.byteLength };
}

/**
 * @param {typeof import("three")} THREE
 * @param {{ thickness?: number, theme?: "light" | "dark" }} [options]
 */
export function createBoardParts(THREE, { thickness = BOARD_THICKNESS_MM, theme = "dark" } = {}) {
  const group = new THREE.Group();
  group.name = "board parts";
  // Each model held, by key: its baked geometry, its materials in each state, the parts that use it.
  const models = new Map();
  const failed = new Map();
  // Each part placed, by reference: what it was placed from, its group, what it waits on.
  const placed = new Map();
  let table = null;
  let scheme = theme === "light" ? "light" : "dark";
  let ink = { hovered: new Set(), selected: new Set(), bright: null };
  const blockFill = new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
  const blockEdge = new THREE.LineBasicMaterial({ transparent: true, toneMapped: false });
  const blockFaded = { fill: blockFill.clone(), edge: blockEdge.clone() };
  const paintBlocks = () => {
    const look = BLOCK_INK[scheme];
    blockFill.color.setHex(look.fill); blockFill.opacity = look.opacity;
    blockEdge.color.setHex(look.edge); blockEdge.opacity = 0.9;
    blockFaded.fill.color.setHex(look.fill); blockFaded.fill.opacity = look.opacity * FADED_OPACITY;
    blockFaded.edge.color.setHex(look.edge); blockFaded.edge.opacity = 0.9 * FADED_OPACITY;
  };
  paintBlocks();

  const surface = rgba => {
    const color = rgba || DEFAULT_SURFACE;
    const alpha = Math.min(Math.max(finite(color[3], 1), 0), 1);
    return new THREE.MeshStandardMaterial({ color: new THREE.Color().setRGB(finite(color[0], 0), finite(color[1], 0), finite(color[2], 0), THREE.LinearSRGBColorSpace),
      roughness: 0.55, metalness: 0, transparent: alpha < 1, opacity: alpha, depthWrite: alpha >= 1, side: THREE.DoubleSide });
  };
  // A model's materials in a state: as authored, lit by the highlight (selected, hovered), or faded; at
  // a placement's own opacity (`opacityOf`), see-through below 1.
  const materialsOf = (model, state, opacity = 1) => {
    const key = opacity < 1 ? `${state}@${opacity}` : state;
    let found = model.materials[key];
    if (found) return found;
    const colors = boardOverlayColors(scheme);
    const tint = new THREE.Color(colors.selection);
    found = model.colors.map(rgba => {
      const material = surface(rgba);
      if (state === "selected" || state === "hovered") {
        material.color.lerp(tint, state === "selected" ? SELECTED_BLEND : HOVER_BLEND);
        material.emissive.copy(tint);
        material.emissiveIntensity = state === "selected" ? 0.12 : 0.05;
      } else if (state === "faded") {
        Object.assign(material, { transparent: true, opacity: material.opacity * FADED_OPACITY, depthWrite: false });
      }
      if (opacity < 1) Object.assign(material, { transparent: true, opacity: material.opacity * opacity, depthWrite: false });
      return material;
    });
    model.materials[key] = found;
    return found;
  };
  const dropMaterials = model => {
    for (const list of Object.values(model.materials)) for (const material of list) material.dispose();
    model.materials = {};
  };

  // A block over a part's outline (sheet millimetres) on its side's face, standing out of it.
  const block = part => {
    const ring = (part.outline || []).map(([x, y]) => new THREE.Vector2(x, -y));
    if (ring.length < 3) return null;
    const geometry = new THREE.ExtrudeGeometry(new THREE.Shape(ring), { depth: BLOCK_HEIGHT_MM, bevelEnabled: false });
    const edges = new THREE.EdgesGeometry(geometry, 30);
    const fill = new THREE.Mesh(geometry, blockFill);
    const rim = new THREE.LineSegments(edges, blockEdge);
    rim.raycast = () => {};
    const holder = new THREE.Group();
    holder.add(fill, rim);
    if (part.side === "bottom") holder.position.z = -thickness - BLOCK_HEIGHT_MM;
    holder.userData.block = { fill, rim };
    return holder;
  };

  const stateOf = ref => (ink.selected.has(ref) ? "selected" : ink.hovered.has(ref) ? "hovered" : ink.bright && !ink.bright.has(ref) ? "faded" : "normal");
  const paint = entry => {
    const state = stateOf(entry.ref);
    for (const body of entry.bodies) {
      const model = models.get(body.key);
      if (model && body.mesh) body.mesh.material = materialsOf(model, state, body.opacity);
    }
    if (entry.block) {
      const faded = state === "faded";
      entry.block.userData.block.fill.material = faded ? blockFaded.fill : blockFill;
      entry.block.userData.block.rim.material = faded ? blockFaded.edge : blockEdge;
    }
  };

  // What a part shows for the table as it is: each visible model's key and matrix, and whether a block stands for the rest.
  const planOf = part => {
    const shown = (part.models || []).filter(model => model && !model.hidden && typeof model.name === "string");
    const bodies = [];
    let missing = false;
    for (const model of shown) {
      const entry = table?.[model.name];
      const key = entry?.document ? `${entry.document}@${entry.stamp || ""}` : "";
      if (key && !failed.has(key)) bodies.push({ key, entry, matrix: modelMatrix(part, model, thickness), opacity: opacityOf(model) });
      else if (table) missing = true;
    }
    return { bodies, missing };
  };

  const unplace = entry => {
    group.remove(entry.group);
    for (const body of entry.bodies) models.get(body.key)?.users.delete(entry.ref);
    if (entry.block) {
      entry.block.userData.block.fill.geometry.dispose();
      entry.block.userData.block.rim.geometry.dispose();
    }
  };
  const place = (part, plan, signature) => {
    const holder = new THREE.Group();
    holder.name = part.ref;
    holder.userData.boardPart = part.ref;
    const entry = { ref: part.ref, signature, group: holder, bodies: [], block: null, part };
    for (const body of plan.bodies) {
      const model = models.get(body.key);
      const mesh = model ? new THREE.Mesh(model.geometry, materialsOf(model, "normal", body.opacity)) : null;
      if (mesh) {
        mesh.matrixAutoUpdate = false;
        mesh.matrix.fromArray(body.matrix);
        mesh.userData.boardPart = part.ref;
        holder.add(mesh);
        model.users.add(part.ref);
      }
      entry.bodies.push({ key: body.key, entry: body.entry, mesh, opacity: body.opacity });
    }
    if (plan.missing) {
      entry.block = block(part);
      if (entry.block) { entry.block.userData.boardPart = part.ref; holder.add(entry.block); }
    }
    group.add(holder);
    paint(entry);
    return entry;
  };
  const release = () => {
    for (const [key, model] of models) {
      if (model.users.size) continue;
      model.geometry.dispose();
      dropMaterials(model);
      models.delete(key);
    }
  };

  let parts = [];
  const update = () => {
    const seen = new Set(), fresh = [];
    for (const part of parts) {
      if (!part?.ref) continue;
      seen.add(part.ref);
      const plan = planOf(part);
      const signature = JSON.stringify([part.at, part.rotation, part.side, part.outline?.length, plan.missing,
        plan.bodies.map(body => [body.key, models.has(body.key), body.opacity])]);
      const was = placed.get(part.ref);
      if (was && was.signature === signature) continue;
      if (was) unplace(was);
      const entry = place(part, plan, signature);
      placed.set(part.ref, entry);
      for (const body of entry.bodies) if (body.mesh) fresh.push({ mesh: body.mesh });
    }
    if (fresh.length) scheduleRuntimeRaycastBvh({ displayRecords: fresh }, { deferUntilRaycast: true });
    for (const [ref, entry] of placed) if (!seen.has(ref)) { unplace(entry); placed.delete(ref); }
    release();
  };

  const pickable = () => [...placed.values()].filter(entry => entry.group.visible).flatMap(entry =>
    [...entry.bodies.map(body => body.mesh).filter(Boolean), ...(entry.block ? [entry.block.userData.block.fill] : [])]);
  const raycaster = new THREE.Raycaster();

  return {
    object3D: group,
    /**
     * The board's parts (the payload's, sheet millimetres) and its models table (`GET …/models`, null
     * until it is in): placed again where they changed. Answers whether anything changed.
     */
    setParts(next, nextTable) {
      parts = Array.isArray(next) ? next : [];
      table = nextTable && typeof nextTable === "object" ? nextTable : null;
      update();
    },
    /**
     * The models a placement waits on: `{ key, document, api }`, each once, the largest parts' first
     * (by the area of their outlines' boxes), so the board fills in from its biggest bodies.
     */
    wanted() {
      const found = new Map();
      for (const entry of placed.values()) {
        const size = outlineArea(entry.part);
        for (const body of entry.bodies) {
          if (body.mesh || models.has(body.key) || failed.has(body.key)) continue;
          const had = found.get(body.key);
          if (!had) found.set(body.key, { key: body.key, document: body.entry.document, api: body.entry.api, file: body.entry.file, size });
          else had.size = Math.max(had.size, size);
        }
      }
      return [...found.values()].sort((a, b) => b.size - a.size).map(({ size, ...item }) => item);
    },
    /** A model baked (`bakeModel`): every placement waiting on it takes it. */
    addModel(key, baked) {
      if (models.has(key)) { baked.geometry.dispose(); return; }
      models.set(key, { ...baked, materials: {}, users: new Set() });
      update();
    },
    /** A model that would not load: its placements stand as blocks. */
    failModel(key, reason) {
      failed.set(key, String(reason || "unreadable"));
      update();
    },
    /**
     * The highlight: the references hovered and selected (`#R1` as `R1`), and the parts that stay bright
     * while something is isolated (null: nothing is). Answers whether anything is painted otherwise.
     */
    setInk({ hovered = [], selected = [], bright = null } = {}) {
      const next = { hovered: new Set(hovered), selected: new Set(selected), bright: bright ? new Set(bright) : null };
      const same = (a, b) => a.size === b.size && [...a].every(value => b.has(value));
      if (same(next.hovered, ink.hovered) && same(next.selected, ink.selected)
        && (next.bright === ink.bright || (next.bright && ink.bright && same(next.bright, ink.bright)))) return false;
      ink = next;
      for (const entry of placed.values()) paint(entry);
      return true;
    },
    /** The theme the blocks and the highlight are drawn in. */
    setTheme(next) {
      const value = next === "light" ? "light" : "dark";
      if (value === scheme) return;
      scheme = value;
      paintBlocks();
      for (const model of models.values()) dropMaterials(model);
      for (const entry of placed.values()) paint(entry);
    },
    /** Shown or not (the Layers tab's 3D models): hidden, they take no pointer either. */
    setVisible(visible) { group.visible = Boolean(visible); },
    get visible() { return group.visible; },
    /** The nearest body or block a ray meets: its part's reference, where and how far. Null for none. */
    pick(ray) {
      if (!group.visible) return null;
      group.updateMatrixWorld(true);
      raycaster.ray.copy(ray);
      const hit = raycaster.intersectObjects(pickable(), false)[0];
      return hit ? { ref: hit.object.userData.boardPart || hit.object.parent?.parent?.userData.boardPart || hit.object.parent?.userData.boardPart,
        point: hit.point.toArray(), distance: hit.distance } : null;
    },
    /** What is held: placements with a body, blocks, distinct models, their triangles as drawn and the bytes of their geometry. */
    stats() {
      let bodies = 0, blocks = 0, drawn = 0;
      for (const entry of placed.values()) {
        const shown = entry.bodies.filter(body => body.mesh);
        if (shown.length) bodies += 1;
        if (entry.block) blocks += 1;
        for (const body of shown) drawn += models.get(body.key)?.triangles || 0;
      }
      let bytes = 0;
      for (const model of models.values()) bytes += model.bytes;
      return { bodies, blocks, models: models.size, failed: failed.size, failure: failed.values().next().value || "", triangles: drawn, bytes,
        waiting: this.wanted().length };
    },
    dispose() {
      for (const entry of placed.values()) unplace(entry);
      placed.clear();
      for (const model of models.values()) { model.geometry.dispose(); dropMaterials(model); }
      models.clear();
      for (const material of [blockFill, blockEdge, blockFaded.fill, blockFaded.edge]) material.dispose();
    }
  };
}

/**
 * The page's side of the models: each wanted model (`wanted()`'s `{ key, document }`) opened by its
 * document id (`open`: the client's `engineDocument`, which waits out the engine's first read of the
 * STEP), read (`loadXbfDocument`), baked and handed to `onModel(key, baked)`; at most `concurrency` at
 * once, a key asked again while it is queued or loading not asked twice. Once in, a key is the parts'
 * (`wanted()` asks only for what they do not hold), so one they let go and want again is loaded again.
 * A failure is `onFailed(key, message)`. No version is waited on: the engine may let the model go; the page has its triangles.
 *
 * @param {typeof import("three")} THREE
 * @param {{ open(document: string, options: { signal: AbortSignal }): Promise<{ url: string, fetch?: typeof fetch }>,
 *   onModel(key: string, baked: ReturnType<typeof bakeModel>): void, onFailed(key: string, message: string): void,
 *   concurrency?: number }} options
 */
export function createModelLoader(THREE, { open, onModel, onFailed, concurrency = 4 }) {
  const controller = new AbortController();
  // The keys queued or loading: what a request does not ask for again.
  const queue = [], asked = new Set();
  let running = 0;
  const timings = { loaded: 0, failed: 0, ms: 0, bytes: 0 };
  const next = () => {
    while (running < concurrency && queue.length && !controller.signal.aborted) {
      const item = queue.shift();
      running += 1;
      const started = performance.now();
      (async () => {
        const served = await open(item.document, { signal: controller.signal });
        // The board's bodies wear their own materials: the engine's look of its display modes is not read.
        const previous = { look: NO_LOOK, source: { base: xbfDocumentSource(served.url).base } };
        const document = await loadXbfDocument(served.url, { fetch: served.fetch, signal: controller.signal, previous });
        try {
          if (controller.signal.aborted) return;
          const baked = bakeModel(THREE, document);
          timings.bytes += document.load.bytes;
          timings.loaded += 1;
          asked.delete(item.key); // the parts' from here on: one they let go is asked for again
          onModel(item.key, baked);
        } finally {
          document.release();
        }
      })().catch(error => {
        if (controller.signal.aborted) return;
        timings.failed += 1;
        asked.delete(item.key);
        onFailed(item.key, error instanceof Error ? error.message : String(error));
      }).finally(() => {
        asked.delete(item.key);
        running -= 1;
        timings.ms = Math.max(timings.ms, performance.now() - started);
        next();
      });
    }
  };
  return {
    /** Ask for these (`wanted()`'s): a key already queued or loading is not asked for again. */
    request(wanted) {
      for (const item of wanted) if (!asked.has(item.key)) { asked.add(item.key); queue.push(item); }
      next();
    },
    /** Asked for, still loading or queued. */
    get pending() { return running + queue.length; },
    stats: () => ({ ...timings, pending: running + queue.length }),
    dispose() { controller.abort(); queue.length = 0; }
  };
}
