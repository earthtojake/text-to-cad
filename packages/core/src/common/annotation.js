import { createScreenSpaceLineStrip } from "./renderEdges.js";

// An annotation: ink drawn over a model in the CAD Viewer's Annotate tool, in 3D. The viewer draws it live
// and writes it with a prompt; a snapshot job draws it over the model it renders (`job.annotation`),
// with this same code, so what an agent renders is what the person drew.
//
// Every mark is in model coordinates and stays where it was drawn, whatever the scene does to the
// parts — exploded, posed, hidden. Clip cuts it as it cuts the model.

/**
 * @typedef {"stroke" | "area" | "text"} AnnotationMarkKind
 * @typedef {{
 *   id: string, kind: AnnotationMarkKind, view?: string,
 *   points: ArrayLike<number>, color: string, opacity?: number,
 *   width?: number, widths?: ArrayLike<number>, closed?: boolean, group?: string,
 *   outline?: number, triangles?: ArrayLike<number>,
 *   text?: string, fontPx?: number,
 *   touches?: { part: string, ref?: string }[]
 * }} AnnotationMark
 *   `points`: x, y, z triples, in model coordinates. A stroke's are its line; an area's (a fill) its outline (the first `outline`) then the points inside
 *   it its `triangles` index; a text mark's its label's four corners. `width`: a stroke's thickness in
 *   screen pixels, at any zoom; `widths`: the pen's, each point's share of it. `fontPx`: a text mark's
 *   size on screen as it was written. `view`: the label of the view it was drawn in. `touches`: what
 *   it was drawn over, most first: a part, with the face or edge of it (`ref`, a prompt reference)
 *   where the view could name one. What it touches says what it is about; its points alone say where.
 * @typedef {{ units: string, marks: AnnotationMark[] }} Annotation
 */

export const ANNOTATION_MARK_KINDS = Object.freeze(["stroke", "area", "text"]);
const COLOR = /^#[0-9a-f]{6}$/i;
// A capture's ink is as heavy against its height as it was on a viewer this tall.
export const ANNOTATION_REFERENCE_HEIGHT_PX = 900;
// Ink is drawn after the model and everything that marks it (a highlighted or ghosted part draws at
// 23–30): it writes no depth, so a part drawn after it would paint over it. Its own depth test still
// hides it behind the model.
export const ANNOTATION_RENDER_ORDER = 40;
// Ink the model hides still shows, this faint: a mark lies exactly on its plane, which may run
// through the model (a profile through a part's middle), and is never lost behind it.
export const ANNOTATION_HIDDEN_OPACITY = 0.3;

const fail = message => { throw new Error(`annotation: ${message}`); };
const numbers = (value, label) => {
  if (!(Array.isArray(value) || ArrayBuffer.isView(value)) || !Array.from(value).every(Number.isFinite)) fail(`${label} must be an array of numbers`);
  return Array.from(value);
};

/**
 * An annotation as it is read from a file or a job: checked field by field, each refusal naming what is
 * wrong. Unknown fields are refused too, so a misspelt one never passes for a default.
 * @param {unknown} raw
 * @returns {Annotation}
 */
export function normalizeAnnotation(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) fail("an annotation is an object with units and marks");
  for (const key of Object.keys(raw)) if (!["units", "marks"].includes(key)) fail(`unknown field "${key}"`);
  const units = String(raw.units ?? "mm");
  if (!Array.isArray(raw.marks)) fail("marks must be an array");
  const ids = new Set();
  const marks = raw.marks.map((mark, index) => {
    const at = `marks[${index}]`;
    if (!mark || typeof mark !== "object") fail(`${at} must be an object`);
    for (const key of Object.keys(mark)) {
      if (!["id", "kind", "view", "points", "color", "opacity", "width", "widths", "closed", "group",
        "outline", "triangles", "text", "fontPx", "touches"].includes(key)) fail(`${at}: unknown field "${key}"`);
    }
    const id = String(mark.id ?? "");
    if (!id || ids.has(id)) fail(`${at}.id must be a unique, non-empty string`);
    ids.add(id);
    if (!ANNOTATION_MARK_KINDS.includes(mark.kind)) fail(`${at}.kind must be one of ${ANNOTATION_MARK_KINDS.join(", ")}`);
    if (!COLOR.test(String(mark.color ?? ""))) fail(`${at}.color must be a #rrggbb colour`);
    const points = numbers(mark.points, `${at}.points`);
    if (!points.length || points.length % 3) fail(`${at}.points must be x, y, z triples`);
    const count = points.length / 3;
    const out = { id, kind: mark.kind, points, color: mark.color };
    if (mark.view != null) out.view = String(mark.view);
    if (mark.opacity != null) {
      if (!(mark.opacity >= 0 && mark.opacity <= 1)) fail(`${at}.opacity must be between 0 and 1`);
      out.opacity = mark.opacity;
    }
    if (mark.kind === "stroke") {
      if (!(mark.width > 0)) fail(`${at}.width must be a positive number of pixels`);
      out.width = mark.width;
      if (mark.widths != null) {
        out.widths = numbers(mark.widths, `${at}.widths`);
        if (out.widths.length !== count) fail(`${at}.widths must have one value per point`);
      }
      out.closed = Boolean(mark.closed);
      if (count < 2) fail(`${at}: a stroke has at least two points`);
    } else if (mark.kind === "area") {
      out.triangles = numbers(mark.triangles, `${at}.triangles`);
      if (!out.triangles.length || out.triangles.length % 3 || out.triangles.some(index => !Number.isInteger(index) || index < 0 || index >= count)) {
        fail(`${at}.triangles must index its points, three to a triangle`);
      }
      out.outline = mark.outline ?? count;
      if (!Number.isInteger(out.outline) || out.outline < 3 || out.outline > count) fail(`${at}.outline must count its outline's points`);
    } else {
      if (count !== 4) fail(`${at}: a text mark's points are its four corners`);
      out.text = String(mark.text ?? "");
      if (!(mark.fontPx > 0)) fail(`${at}.fontPx must be a positive number of pixels`);
      out.fontPx = mark.fontPx;
    }
    if (mark.group != null) out.group = String(mark.group);
    if (mark.touches != null) {
      if (!Array.isArray(mark.touches) || mark.touches.some(touch => typeof touch?.part !== "string" || (touch.ref != null && typeof touch.ref !== "string"))) {
        fail(`${at}.touches must list { part, ref? } entries`);
      }
      out.touches = mark.touches.map(touch => (touch.ref ? { part: touch.part, ref: touch.ref } : { part: touch.part }));
    }
    return out;
  });
  return { units, marks };
}

const rounded = values => Array.from(values, value => Math.round(value * 1e4) / 1e4);
/**
 * An annotation as it is written: plain JSON, points to a ten-thousandth of a unit.
 * @param {{ units: string, marks: readonly AnnotationMark[] }} annotation
 * @returns {Annotation}
 */
export function annotationDocument({ units, marks }) {
  return {
    units,
    marks: marks.map(mark => {
      const out = { ...mark, points: rounded(mark.points) };
      if (mark.widths) out.widths = rounded(mark.widths);
      if (mark.triangles) out.triangles = Array.from(mark.triangles);
      return out;
    }),
  };
}

/** Whether an object and every parent of it is shown. */
export const annotationObjectShown = object => { for (let node = object; node; node = node.parent) if (!node.visible) return false; return true; };

// The pen's width along a stroke: three's screen-space line widens every segment by one uniform, so
// each segment carries its two ends' shares of it, and the feather the core line adds
// (`renderEdges.js`) is measured against the width there.
function taperedWidths(baseCompile) {
  return function inkTaperedLine(shader, renderer) {
    baseCompile?.call(this, shader, renderer);
    shader.vertexShader = `attribute float instanceWidthStart;\nattribute float instanceWidthEnd;\nvarying float vInkWidth;\n${shader.vertexShader}`
      .replace("void main() {", "void main() {\n\tfloat inkWidth = ( position.y < 0.5 ) ? instanceWidthStart : instanceWidthEnd;\n\tvInkWidth = inkWidth;")
      .replace(/offset \*= linewidth\b/, "offset *= linewidth * inkWidth");
    shader.fragmentShader = `varying float vInkWidth;\n${shader.fragmentShader}`
      .replace("float cadEdgeInkHalfWidth = linewidth * 0.5;", "float cadEdgeInkHalfWidth = linewidth * vInkWidth * 0.5;");
  };
}
let taperedCompile = null;
// A once-only stroke's feather and cap rim (under half its coverage) is left undrawn, so the pixels it would
// write into the stencil never shut out the body of the segment beside it.
function withoutRim(baseCompile) {
  return function inkOnceOnlyLine(shader, renderer) {
    baseCompile?.call(this, shader, renderer);
    shader.fragmentShader = shader.fragmentShader
      .replace("gl_FragColor = vec4( diffuseColor.rgb, alpha );", "if ( alpha < opacity * 0.5 ) discard;\n\t\tgl_FragColor = vec4( diffuseColor.rgb, alpha );");
  };
}
const rimless = new WeakMap();

// A text mark's picture: its words as written, in the UI's face.
function textCanvas(mark) {
  const document = globalThis.document;
  if (!document?.createElement) return null;
  const scale = 2, font = `500 ${mark.fontPx * scale}px ui-sans-serif, system-ui, sans-serif`;
  const lines = String(mark.text).split("\n");
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.font = font;
  const width = Math.max(1, ...lines.map(line => context.measureText(line).width));
  canvas.width = Math.ceil(width) + 2;
  canvas.height = Math.ceil(lines.length * mark.fontPx * 1.25 * scale) + 2;
  context.font = font;
  context.fillStyle = mark.color;
  context.textBaseline = "top";
  lines.forEach((line, index) => context.fillText(line, 1, 1 + index * mark.fontPx * 1.25 * scale));
  return canvas;
}

// A translucent stroke (the highlighter's) is drawn as overlapping round-capped segments, which would darken
// where they meet. Each such stroke gets stencil references of its own (one for the stroke, one for its faint
// hidden part) and draws only where its own reference is not yet written, so its pixels blend once; a
// crossing stroke has another reference, and does blend with it. The references cycle through 1-251: odd for a stroke, even for its hidden part.
let stencilRef = 0;
function onceOnly(THREE, material, ref) {
  const base = material.onBeforeCompile;
  if (!rimless.has(base)) rimless.set(base, withoutRim(base));
  material.onBeforeCompile = rimless.get(base);
  material.stencilWrite = true;
  material.stencilRef = ref;
  material.stencilFunc = THREE.NotEqualStencilFunc;
  material.stencilFail = THREE.KeepStencilOp;
  material.stencilZFail = THREE.KeepStencilOp;
  material.stencilZPass = THREE.ReplaceStencilOp;
  material.needsUpdate = true;
}

/**
 * One mark's object: a stroke a screen-width line along its points, an area a flat mesh of its
 * triangles, a text mark its picture on a quad, where its points are: in model coordinates.
 *
 * @param {{ THREE: typeof import("three"), Line2: any, LineGeometry: any, LineMaterial: any }} context
 * @param {AnnotationMark} mark
 * @param {{ lineScale: number }} options  `lineScale`: device pixels per screen pixel of `width`.
 */
export function annotationMarkObject(context, mark, { lineScale }) {
  const { THREE } = context;
  const positions = mark.points instanceof Float32Array ? mark.points : new Float32Array(mark.points);
  let object;
  if (mark.kind === "stroke") {
    object = createScreenSpaceLineStrip(context, positions, { color: mark.color, opacity: mark.opacity ?? 1,
      lineWidth: Math.max(1, mark.width * lineScale), renderOrder: ANNOTATION_RENDER_ORDER, depthTest: true, depthWrite: false });
    if (object && mark.widths?.length === positions.length / 3) {
      const segments = mark.widths.length - 1;
      object.geometry.setAttribute("instanceWidthStart", new THREE.InstancedBufferAttribute(new Float32Array(Array.from(mark.widths).slice(0, segments)), 1));
      object.geometry.setAttribute("instanceWidthEnd", new THREE.InstancedBufferAttribute(new Float32Array(Array.from(mark.widths).slice(1)), 1));
      // One callback for every tapered line, so they share a program.
      taperedCompile ??= taperedWidths(object.material.onBeforeCompile);
      object.material.onBeforeCompile = taperedCompile;
      object.material.needsUpdate = true;
    }
  } else {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    if (mark.kind === "area") {
      geometry.setIndex(Array.from(mark.triangles));
      const opacity = mark.opacity ?? 1;
      object = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: mark.color, transparent: opacity < 1, opacity,
        side: THREE.DoubleSide, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -4, toneMapped: false }));
    } else {
      geometry.setIndex([0, 1, 2, 0, 2, 3]);
      geometry.setAttribute("uv", new THREE.BufferAttribute(new Float32Array([0, 1, 1, 1, 1, 0, 0, 0]), 2));
      const canvas = textCanvas(mark);
      const material = new THREE.MeshBasicMaterial({ transparent: true, side: THREE.DoubleSide, depthWrite: false, toneMapped: false, visible: Boolean(canvas) });
      if (canvas) {
        material.map = new THREE.CanvasTexture(canvas);
        material.map.colorSpace = THREE.SRGBColorSpace;
      }
      object = new THREE.Mesh(geometry, material);
    }
    object.renderOrder = ANNOTATION_RENDER_ORDER;
  }
  if (object) {
    // Its points are in model coordinates: its world matrix is the identity, never recomputed.
    object.matrixAutoUpdate = false;
    object.matrixWorldAutoUpdate = false;
    object.matrixWorld.identity();
    object.frustumCulled = false;
    // Its hidden part: the same mark drawn faint over everything, before the mark itself is drawn
    // where nothing hides it.
    const hidden = object.clone(false);
    hidden.material = object.material.clone();
    hidden.material.onBeforeCompile = object.material.onBeforeCompile;
    // A screen-space line reads its resolution off the renderer as it is drawn (`renderEdges.js`).
    hidden.onBeforeRender = object.onBeforeRender;
    hidden.material.depthTest = false;
    hidden.material.transparent = true;
    hidden.material.opacity = (object.material.opacity ?? 1) * ANNOTATION_HIDDEN_OPACITY;
    hidden.renderOrder = object.renderOrder - 1;
    if (mark.kind === "stroke" && (mark.opacity ?? 1) < 1 && THREE.NotEqualStencilFunc !== undefined) {
      stencilRef = (stencilRef + 2) % 250;
      onceOnly(THREE, object.material, stencilRef + 1);
      onceOnly(THREE, hidden.material, stencilRef + 2);
    }
    hidden.matrixWorld.identity();
    hidden.userData = { annotationHidden: true };
    object.add(hidden);
  }
  return object;
}

/**
 * Cuts a mark's object with `planes` (Clip's), as the model is cut.
 * @param {import("three").Object3D} object
 * @param {import("three").Plane[]} [planes]
 */
export function clipAnnotationObject(object, planes = []) {
  for (const part of [object, ...object.children.filter(child => child.userData?.annotationHidden)]) {
    const material = part.material;
    if (material && (material.clippingPlanes?.length || 0) !== planes.length) material.needsUpdate = true;
    if (material) material.clippingPlanes = planes.length ? planes : null;
  }
}

/** Frees a mark's object. */
export function disposeAnnotationObject(object) {
  object.removeFromParent();
  object.userData?.beforeDispose?.();
  object.geometry?.dispose?.();
  object.material?.map?.dispose?.();
  object.material?.dispose?.();
  // Its hidden part shares its geometry and picture.
  for (const child of object.children.filter(part => part.userData?.annotationHidden)) child.material?.dispose?.();
}

/**
 * A whole annotation drawn into a scene once, for a still: every mark's object under one group, cut
 * by the clip planes the scene has when `place()` runs.
 *
 * @param {object} context  `THREE` and the screen-space line classes (`annotationMarkObject`).
 * @param {Annotation} annotation  `normalizeAnnotation`'s.
 * @param {{ lineScale: number }} options
 */
export function createAnnotationLayer(context, annotation, options) {
  const { THREE } = context;
  const group = new THREE.Group();
  group.name = "annotation";
  const entries = annotation.marks.map(mark => ({ mark, object: annotationMarkObject(context, mark, options) })).filter(entry => entry.object);
  for (const { object } of entries) group.add(object);
  return {
    group,
    place(planes = []) {
      for (const { object } of entries) clipAnnotationObject(object, planes);
    },
    dispose() {
      for (const { object } of entries) disposeAnnotationObject(object);
      group.removeFromParent();
    },
  };
}
