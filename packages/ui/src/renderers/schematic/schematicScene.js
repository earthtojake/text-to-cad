/**
 * A schematic as the kit's selection hook reads a scene (`kit/tools/select/useSceneSelection.js`): its
 * picks by schematic reference (`#R1`, `#R1.2`, `#net:/MID`, `#wire:<uuid>`, `#sheet:/Load/`: what Quick
 * Edit names and `cad.kicad_sch.read(path).resolve(ref)` reads), each described (`schematicFacts.js`),
 * and its highlight, which `onHighlight` paints — what is hovered and selected, resolved in the
 * hierarchy; the view draws what of it lies on the sheet shown.
 *
 * Importing this module has no environmental effects.
 */
import { describeSchematicReference } from "./schematicFacts.js";

/**
 * @param {ReturnType<typeof import("@cad/core/lib/schematic2d/schematicIndex.js").createSchematicIndex>} index
 * @param {{ onHighlight(ink: { hovered: object[], selected: object[] }): void, t?: Function }} options
 */
export function createSchematicScene(index, { onHighlight, t }) {
  const resolved = ids => ids.map(id => index.resolve(id)).filter(Boolean);
  return {
    hasPart: id => Boolean(index.resolve(id)),
    describePart: id => describeSchematicReference(index.resolve(id), index, t),
    setHighlight({ hovered = [], selected = [] } = {}) {
      onHighlight({ hovered: resolved(hovered), selected: resolved(selected) });
    }
  };
}
