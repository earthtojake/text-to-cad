import { english } from "../../i18n/core.js";
/**
 * What a drawing's picks are called, and what the viewer says of them: a DXF's references.
 *
 * A reference names one modelspace entity by its HANDLE, the id DXF gives every entity and keeps
 * across saves: `bracket.dxf#h2F` is the entity whose handle is 2F. The payload names the
 * top-level entity for everything it draws (`cad_server.drawing_payload`), so a pick of anything a
 * block reference draws is its INSERT, and a dimension is one reference. That is the whole
 * grammar: no faces, no edges, nothing to resolve — an agent finds `2F` in the file with any DXF
 * reader (`doc.entitydb["2F"]` in ezdxf). Quick Edit's chip reads it as a person would: its type
 * and layer ("Circle on CUT", "Block BOLT on HARDWARE").
 *
 * Importing this module has no environmental effects.
 */

const HANDLE = /^[0-9A-F]+$/i;
const REFERENCE = /^h([0-9A-F]+)$/i;

/** The reference id of the entity with `handle`: `h2F`. */
export const drawingReferenceId = handle => `h${String(handle).toUpperCase()}`;

/** The handle a reference id names (`h2F` → `2F`), or "" for an id that is no drawing's. */
export function drawingHandleOf(id) {
  const match = REFERENCE.exec(String(id || "").trim());
  return match ? match[1].toUpperCase() : "";
}

// Each DXF type's name as a person says it, by its key (`drawing.type.*`); the type itself is the DXF's.
const TYPE_KEYS = Object.freeze({
  LINE: "line", ARC: "arc", CIRCLE: "circle", ELLIPSE: "ellipse", SPLINE: "spline", LWPOLYLINE: "polyline",
  POLYLINE: "polyline", POINT: "point", TEXT: "text", MTEXT: "text", HATCH: "hatch", SOLID: "solid",
  DIMENSION: "dimension", LEADER: "leader", MULTILEADER: "leader", INSERT: "block", IMAGE: "image",
  WIPEOUT: "wipeout", RAY: "ray", XLINE: "constructionLine", "3DFACE": "face", TRACE: "trace"
});

/** An entity's kind, as a person says it in `t`'s language: "Circle", "Block BOLT", or its DXF type for anything rarer. */
export function entityKind(entity, t = english) {
  const type = String(entity?.type || "");
  if (type === "INSERT") return entity.block ? t("drawing.blockNamed", { name: entity.block }) : t("drawing.type.block");
  return TYPE_KEYS[type] ? t(`drawing.type.${TYPE_KEYS[type]}`) : type || t("drawing.entity");
}

/** An entity as Quick Edit's chip names it: its kind, on its layer. */
export const entityName = (entity, t = english) => t("drawing.onLayer", { kind: entityKind(entity, t), layer: entity.layer || "0" });

const round = value => String(Math.round(Number(value) * 1e4) / 1e4);

// The length of what an entity drew where it is straight segments alone (a line, a polyline of lines):
// its `lines` runs, and its paths of moves and lines; null where it drew a curve or nothing to measure.
function strokedLength(entity) {
  let length = 0, measured = false;
  const run = (points) => {
    for (let at = 2; at + 1 < points.length; at += 2) length += Math.hypot(points[at] - points[at - 2], points[at + 1] - points[at - 1]);
  };
  for (const primitive of entity.primitives || []) {
    if (primitive.type === "lines") { for (const line of primitive.geometry) run(line); measured = true; continue; }
    if (primitive.type !== "path") return null;
    let last = null, start = null;
    for (const command of primitive.geometry) {
      const [op, x, y] = command;
      if (op === "M") { last = [x, y]; start = last; } else if (op === "L" && last) { length += Math.hypot(x - last[0], y - last[1]); last = [x, y]; } else if (op === "Z" && last && start) { length += Math.hypot(start[0] - last[0], start[1] - last[1]); last = start; } else return null;
    }
    measured = true;
  }
  return measured ? length : null;
}

// What an entity measures, by its kind: a line's or a straight polyline's length, a circle's diameter, and
// the size of its box for anything else that has one (an arc, a text, a block reference, a hatch).
function entityMeasures(entity) {
  const type = String(entity.type || "");
  const straight = type === "LINE" || type === "LWPOLYLINE" || type === "POLYLINE" ? strokedLength(entity) : null;
  const box = entity.box;
  const size = box && type !== "LINE" && type !== "CIRCLE" && type !== "POINT" ? [box[2] - box[0], box[3] - box[1]] : null;
  return { length: straight, diameter: type === "CIRCLE" && entity.radius != null ? 2 * entity.radius : null, size };
}

/**
 * An entity, as Quick Edit's chip and the Selected pane say it: its name, and what the drawing says of it
 * — its handle and DXF type, its layer, the block an INSERT places, a circle's or arc's centre and radius,
 * and what it measures (a straight run's length, a circle's diameter, else the size of its box) in the
 * drawing's unit; for the hover tip, its headline measure ("25 mm", "Ø 12 mm").
 * @param {import("@cad/core/lib/drawing2d/drawing.js").DrawingEntity} entity
 */
export function describeEntity(entity, unit = "", t = english) {
  const units = unit ? ` ${unit}` : "";
  const { length, diameter, size } = entityMeasures(entity);
  const tip = length !== null ? `${round(length)}${units}` : diameter !== null ? `Ø ${round(diameter)}${units}`
    : entity.radius != null ? `R ${round(entity.radius)}${units}` : "";
  return {
    name: entityName(entity, t),
    tip,
    facts: [
      { label: t("drawing.handle"), value: entity.handle },
      { label: t("drawing.typeLabel"), value: entity.type || "—" },
      { label: t("drawing.layer"), value: entity.layer || "0" },
      ...(entity.block ? [{ label: t("drawing.type.block"), value: entity.block }] : []),
      ...(entity.center ? [{ label: t("drawing.centre"), value: `${round(entity.center[0])}, ${round(entity.center[1])}` }] : []),
      ...(entity.radius != null ? [{ label: t("drawing.radius"), value: `${round(entity.radius)}${units}` }] : []),
      ...(diameter !== null ? [{ label: t("measure.diameter"), value: `${round(diameter)}${units}` }] : []),
      ...(length !== null ? [{ label: t("measure.length"), value: `${round(length)}${units}` }] : []),
      ...(size ? [{ label: t("part.size"), value: `${round(size[0])} × ${round(size[1])}${units}` }] : [])
    ]
  };
}

/**
 * An entity, as the frame reads a pick (`kit/inspector/inspect.js`'s `DetailItem`): `describeEntity`'s name,
 * tip and facts, its reference id as its ID, and, for a block reference, the other references of its
 * block as what it is connected to (the payload names a block reference's contents by the reference, so
 * they are not picks of their own); nothing for any other entity.
 */
export function describeDrawingPick(drawing, id, unit = "", t = english) {
  const handle = drawingHandleOf(id);
  const entity = handle && HANDLE.test(handle) ? drawing.entities.get(handle) : null;
  if (!entity) return null;
  const described = describeEntity(entity, unit, t);
  const others = entity.type === "INSERT" && entity.block
    ? [...drawing.entities.values()].filter(other => other.type === "INSERT" && other.block === entity.block && other.handle !== entity.handle) : [];
  return {
    id: `entity:${handle}`, pick: drawingReferenceId(handle), kind: entity.type === "INSERT" ? "block" : "", title: described.name, tip: described.tip, ref: drawingReferenceId(handle),
    facts: described.facts,
    related: others.length ? { title: t("drawing.sameBlock", { name: entity.block }), count: String(others.length),
      rows: others.map(other => ({ id: other.handle, kind: "block", pick: drawingReferenceId(other.handle), label: `#${other.handle}`, detail: other.layer || "0" })) } : null
  };
}

/**
 * A drawing as the kit's selection and reference hooks read a scene (`useSceneSelection`,
 * `useSceneReferences`): its entities by reference id, each described, and its highlight, which
 * `onHighlight` paints.
 *
 * @param {import("@cad/core/lib/drawing2d/drawing.js").PreparedDrawing} drawing
 * @param {{ onHighlight(ink: { hovered: string[], selected: string[] }): void, unit?: string }} options
 *   `onHighlight` is given handles; `t` says the entities in the view's language.
 */
export function createDrawingScene(drawing, { onHighlight, unit = "", t = english }) {
  const entityOf = id => {
    const handle = drawingHandleOf(id);
    return handle && HANDLE.test(handle) ? drawing.entities.get(handle) || null : null;
  };
  const handles = ids => ids.map(drawingHandleOf).filter(handle => drawing.entities.has(handle));
  return {
    hasPart: id => entityOf(id) !== null,
    describePart(id) {
      const entity = entityOf(id);
      return entity ? describeEntity(entity, unit, t) : null;
    },
    setHighlight({ hovered = [], selected = [] } = {}) {
      onHighlight({ hovered: handles(hovered), selected: handles(selected) });
    }
  };
}

// `$INSUNITS` codes to the abbreviation a measurement is read in. The ones a part is drawn in;
// any other is said by the name the payload gives it.
const UNIT_ABBREVIATIONS = Object.freeze({
  1: "in", 2: "ft", 3: "mi", 4: "mm", 5: "cm", 6: "m", 7: "km", 8: "µin", 9: "mil", 10: "yd", 13: "µm", 14: "dm"
});
/** What a reading in a drawing that declares no unit is said in: the drawing's own units. */
export const UNITLESS = "units";

/**
 * The unit a drawing's coordinates are in, as its `$INSUNITS` says (the payload's `units`):
 * `{ unit, declared }`. A drawing that declares none (`$INSUNITS` 0, or a code with no name) is
 * read in bare drawing units, never assumed to be millimetres.
 * @param {{ insunits?: number, name?: string } | null | undefined} units
 */
export function drawingUnits(units) {
  const code = Number(units?.insunits) || 0;
  const unit = UNIT_ABBREVIATIONS[code] || (code ? String(units?.name || "").toLowerCase() : "");
  return unit ? { unit, declared: true } : { unit: UNITLESS, declared: false };
}

/** A Layers section is worth its tile from this many layers, or with any block reference in it. */
export const LAYERS_SECTION_MIN_LAYERS = 4;

/**
 * Whether a drawing has the structure a Layers section is for: several layers to show and hide
 * (`LAYERS_SECTION_MIN_LAYERS` or more drawn on), or block references, whose contents a layer
 * nests. A flat pattern of two or three layers (CUT, BEND) and no blocks has none: its section
 * would be a few rows saying what the drawing already shows.
 * @param {import("@cad/core/lib/drawing2d/drawing.js").PreparedDrawing | null} drawing
 */
export function layersSectionShown(drawing) {
  if (!drawing) return false;
  if (drawing.layers.length >= LAYERS_SECTION_MIN_LAYERS) return true;
  for (const entity of drawing.entities.values()) if (entity.type === "INSERT") return true;
  return false;
}

/**
 * The Layers section's rows: each layer drawn on, in the drawing's order, with its colour, the
 * number of entities drawn on it, and the block references placed on it (each a row of its own,
 * its block's name).
 * @param {import("@cad/core/lib/drawing2d/drawing.js").PreparedDrawing} drawing
 * @returns {{ name: string, color: string | null, entities: number, inserts: { handle: string, block: string }[] }[]}
 */
export function layerRows(drawing) {
  const inserts = new Map();
  for (const entity of drawing.entities.values()) {
    if (entity.type !== "INSERT") continue;
    if (!inserts.has(entity.layer)) inserts.set(entity.layer, []);
    inserts.get(entity.layer).push({ handle: entity.handle, block: entity.block || "" });
  }
  const rows = drawing.layers.map(layer => ({
    name: String(layer.name),
    color: layer.color ?? null,
    entities: Number(layer.entities) || 0,
    inserts: inserts.get(String(layer.name)) || []
  }));
  // A block reference whose contents all sit on other layers drew nothing on its own: its layer is
  // still where it was placed, and is a row for it.
  for (const [name, placed] of inserts) {
    if (!rows.some(row => row.name === name)) rows.push({ name, color: null, entities: placed.length, inserts: placed });
  }
  return rows;
}
