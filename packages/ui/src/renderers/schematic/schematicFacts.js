import { english } from "@cad/ui/i18n";
/**
 * What a schematic says of a reference (`schematicIndex.js`'s `resolve`): a pick's name, as the
 * schematic names it, its kind's glyph (`schematicReferences.jsx`) and its card's facts — a part's
 * value, footprint, symbol and sheets; a pin's name, type and net; a net's pins and sheets; a sheet's
 * file and page; a label's kind and net; a wire's net.
 */

const KIND_KEYS = Object.freeze({
  wire: "schematic.text.wire", bus: "schematic.text.bus", junction: "schematic.text.junction",
  no_connect: "schematic.text.no_connect", bus_entry: "schematic.text.bus_entry", symbol: "schematic.text.symbol"
});

/** The id a chip shows: the reference without its '#'. */
export const schematicReferenceId = selector => String(selector || "").replace(/^#/, "");

/**
 * @param {object | null} resolved
 * @param {ReturnType<typeof import("@cad/core/lib/schematic2d/schematicIndex.js").createSchematicIndex>} index
 */
export function describeSchematicReference(resolved, index, t = english) {
  if (!resolved) return null;
  const sheets = list => list.map(path => index.sheetName(path)).join(", ");
  const fact = (label, value) => (value === undefined || value === null || value === "" ? null : { label, value: String(value) });
  const facts = (...rows) => rows.filter(Boolean);
  if (resolved.kind === "part") {
    const { part } = resolved;
    return { name: part.ref, glyph: "part", facts: facts(fact(t("schematic.text.value"), part.value), fact(t("schematic.text.footprint"), part.footprint),
      fact(t("schematic.text.symbol"), part.lib_id), fact("MPN", part.mpn || part.fields?.MPN), fact(t("schematic.text.sheets"), sheets(resolved.sheets))) };
  }
  if (resolved.kind === "pin") {
    const { pin } = resolved;
    return { name: `${pin.part}.${pin.number}`, glyph: "pin", facts: facts(fact(t("schematic.text.pin_name"), pin.name && pin.name !== "~" ? pin.name : ""),
      fact(t("schematic.text.type"), pin.type), fact(t("schematic.text.net"), pin.net), fact(t("schematic.text.sheet"), sheets(resolved.sheets))) };
  }
  if (resolved.kind === "net") {
    return { name: t("schematic.text.net_name", { name: resolved.net }), glyph: "net",
      facts: facts(fact(t("schematic.text.pins"), resolved.netInfo.pins.length), fact(t("schematic.text.sheets"), sheets(resolved.sheets))) };
  }
  if (resolved.kind === "sheet") {
    return { name: resolved.label, glyph: "sheet", facts: facts(fact(t("schematic.text.file"), resolved.sheet.file), fact(t("schematic.text.page"), resolved.sheet.page),
      fact(t("schematic.text.path"), resolved.path)) };
  }
  if (resolved.kind === "label") {
    const { item } = resolved;
    return { name: `“${item.text}”`, glyph: "label", facts: facts(fact(t("schematic.text.kind"), item.label), fact(t("schematic.text.net"), item.net),
      fact(t("schematic.text.sheet"), sheets(resolved.sheets))) };
  }
  const kind = t(KIND_KEYS[resolved.kind] || "schematic.text.wire");
  return { name: resolved.net ? `${resolved.net} · ${kind}` : kind, glyph: resolved.kind,
    facts: facts(fact(t("schematic.text.net"), resolved.net), fact(t("schematic.text.sheet"), sheets(resolved.sheets))) };
}
