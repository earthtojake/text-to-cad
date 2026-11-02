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

/**
 * An entity, as Quick Edit's chip says it: its name, and what the drawing says of it — its handle
 * and DXF type, its layer, the block an INSERT places, a circle's or arc's centre and radius.
 * @param {import("@cad/core/lib/drawing2d/drawing.js").DrawingEntity} entity
 */
export function describeEntity(entity, unit = "", t = english) {
  const units = unit ? ` ${unit}` : "";
  return {
    name: entityName(entity, t),
    facts: [
      { label: t("drawing.handle"), value: entity.handle },
      { label: t("drawing.typeLabel"), value: entity.type || "—" },
      { label: t("drawing.layer"), value: entity.layer || "0" },
      ...(entity.block ? [{ label: t("drawing.type.block"), value: entity.block }] : []),
      ...(entity.center ? [{ label: t("drawing.centre"), value: `${round(entity.center[0])}, ${round(entity.center[1])}` }] : []),
      ...(entity.radius != null ? [{ label: t("drawing.radius"), value: `${round(entity.radius)}${units}` }] : [])
    ]
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
