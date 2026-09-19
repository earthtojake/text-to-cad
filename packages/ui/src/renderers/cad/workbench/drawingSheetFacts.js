/**
 * What a drawing SHEET says about itself, read from the drawing alone.
 *
 * A dimensioned sheet written by cadgen's @drawing carries a frame on its SHEET
 * layer and a title block on TITLE: the title, a part-number line, and two
 * right-aligned lines, "SCALE 1:2   MM   THIRD ANGLE" and "SHEET 1 OF 2   REV A
 * ...". Those are facts of the document (paper, scale, units, projection,
 * revision), so the Sheet tab shows them as read-only fields. Nothing here
 * points outside the file: the facts come from the parsed geometry only.
 *
 * A DXF without a frame or title block yields whatever subset it does state; a
 * drawing from another tool gets paper size from its SHEET frame when it has
 * one and nothing else, which is honest.
 */

/** ISO 216 sheets in millimetres (landscape); portrait matches by swapping. */
export const DRAWING_SHEET_SIZES = Object.freeze([
  { name: "A4", widthMm: 297, heightMm: 210 },
  { name: "A3", widthMm: 420, heightMm: 297 },
  { name: "A2", widthMm: 594, heightMm: 420 },
  { name: "A1", widthMm: 841, heightMm: 594 },
  { name: "A0", widthMm: 1189, heightMm: 841 }
]);

/** The @drawing frame sits this far inside the paper edge, so paper = frame + 2 × margin. */
const SHEET_FRAME_MARGIN_MM = 10;
const SIZE_TOLERANCE_MM = 1.5;

function isLayer(record, name) {
  return String(record?.layer || "").trim().toUpperCase() === name;
}

function sheetFrameBounds(geometry) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const line of Array.isArray(geometry?.lines) ? geometry.lines : []) {
    if (!isLayer(line, "SHEET")) continue;
    for (const point of [line.start, line.end]) {
      const x = Number(point?.[0]);
      const y = Number(point?.[1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }
  if (!Number.isFinite(minX) || maxX - minX <= 0 || maxY - minY <= 0) {
    return null;
  }
  return { widthMm: maxX - minX, heightMm: maxY - minY };
}

/** Name a paper size from its frame, or describe it in millimetres when it is none of them. */
export function paperSizeLabel(frame) {
  if (!frame) return "";
  const width = frame.widthMm + 2 * SHEET_FRAME_MARGIN_MM;
  const height = frame.heightMm + 2 * SHEET_FRAME_MARGIN_MM;
  for (const size of DRAWING_SHEET_SIZES) {
    const landscape = Math.abs(width - size.widthMm) <= SIZE_TOLERANCE_MM && Math.abs(height - size.heightMm) <= SIZE_TOLERANCE_MM;
    const portrait = Math.abs(width - size.heightMm) <= SIZE_TOLERANCE_MM && Math.abs(height - size.widthMm) <= SIZE_TOLERANCE_MM;
    if (landscape || portrait) {
      return `${size.name} · ${Math.round(width)} × ${Math.round(height)} mm`;
    }
  }
  return `${Math.round(width)} × ${Math.round(height)} mm`;
}

const SCALE_LINE = /^SCALE\s+(\S+)\s+(\S+)\s+(.+?)\s*$/i;
const SHEET_LINE = /^SHEET\s+(\d+)\s+OF\s+(\d+)\s+REV\s+(\S+)/i;

/**
 * @param {object} dxfData the parsed drawing (parseDxf output)
 * @returns {{paper:string, scale:string, units:string, projection:string, revision:string,
 *   sheet:string, title:string, partNumber:string, hasFrame:boolean, hasTitleBlock:boolean}}
 */
export function drawingSheetFacts(dxfData) {
  const geometry = dxfData?.geometry;
  const frame = sheetFrameBounds(geometry);
  const facts = {
    paper: paperSizeLabel(frame),
    scale: "",
    units: "",
    projection: "",
    revision: "",
    sheet: "",
    title: "",
    partNumber: "",
    hasFrame: Boolean(frame),
    hasTitleBlock: false
  };
  const titleTexts = (Array.isArray(geometry?.texts) ? geometry.texts : [])
    .filter((text) => isLayer(text, "TITLE") && String(text.value || "").trim());
  if (!titleTexts.length) {
    return facts;
  }
  facts.hasTitleBlock = true;
  const remaining = [];
  for (const text of titleTexts) {
    const value = String(text.value).trim();
    const scaleMatch = value.match(SCALE_LINE);
    if (scaleMatch) {
      facts.scale = scaleMatch[1];
      facts.units = scaleMatch[2].toLowerCase();
      facts.projection = scaleMatch[3].replace(/\s+/g, " ").toLowerCase();
      continue;
    }
    const sheetMatch = value.match(SHEET_LINE);
    if (sheetMatch) {
      facts.sheet = `${Number(sheetMatch[1])} of ${Number(sheetMatch[2])}`;
      facts.revision = sheetMatch[3];
      continue;
    }
    remaining.push({ value, heightMm: Number(text.heightMm) || 0 });
  }
  // The title is the tallest text left in the block; the part-number line is the next one.
  remaining.sort((a, b) => b.heightMm - a.heightMm);
  facts.title = remaining[0]?.value || "";
  facts.partNumber = remaining[1]?.value || "";
  return facts;
}
