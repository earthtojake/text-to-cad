import { DOCUMENT_TYPE_REGISTRY } from "./documentTypes.generated.js";
import { RENDER_FORMAT, normalizeFormat } from "./fileFormats.js";

// WHAT EACH RENDER FORMAT CAN DO — one table, so viewer code asks "can this format
// do X?" instead of "is this format Y?".
//
// Every identity check spread through the client (`renderFormat === RENDER_FORMAT.DXF`,
// `isMeshRenderFormat(...)`, the `xxxMode` boolean piles) is a place a new format has to
// be hand-added and a place an improvement fails to reach the other formats. That is not
// hypothetical: the Orbit button was gated off per format independently and had to be
// fixed twice, and one format grew a whole parallel export route to an endpoint the server
// does not implement. Both were "this format was not on the list" bugs.
//
// So: a format is a ROW here plus a renderer (packages/ui/docs/render-types.md). Shared
// behaviour reads this table; it is never re-derived from the format's identity.
//
// Rules for changing this file:
// - Add a capability when the SECOND format needs it, never speculatively, with its reader;
//   take a column out with its last reader. Today one column has one: `iconKind`.
// - Capabilities are DATA. No behaviour, no imports beyond the format enum.
// - What a 3D file's tools and view offer (Measure, Clip, Explode, the display modes) is
//   not here: each renderer offers its tools, and `viewFeaturesForKind`
//   (`common/viewSettings.js`) is the one rule of what a file's view offers.

// The file-list glyph. A table rather than a cascade of format tests: the icon is the most
// purely per-format fact in the client, and it was the longest identity cascade.
export const ENTRY_ICON_KIND = Object.freeze({
  LOADING: "loading",
  DXF: "dxf",
  KICAD_PCB: "kicad_pcb",
  ROBOT: "robot",
  STEP: "step",
  STL_MESH: "stl-mesh",
  THREE_MF_MESH: "3mf-mesh",
  GLB_MESH: "glb-mesh"
});

const DEFAULT_CAPABILITIES = Object.freeze({ iconKind: ENTRY_ICON_KIND.STEP });
const ROBOT_CAPABILITIES = Object.freeze({ iconKind: ENTRY_ICON_KIND.ROBOT });

// A mesh's icon is its own format's; every other type's is its view's (`cad.registry`).
const MESH_ICONS = Object.freeze({
  [RENDER_FORMAT.STL]: ENTRY_ICON_KIND.STL_MESH,
  [RENDER_FORMAT.THREE_MF]: ENTRY_ICON_KIND.THREE_MF_MESH,
  [RENDER_FORMAT.GLB]: ENTRY_ICON_KIND.GLB_MESH
});
const VIEW_CAPABILITIES = Object.freeze({
  // An engine document (`packages/ui/src/renderers/xbf`), which a STEP opens as: one icon.
  document: DEFAULT_CAPABILITIES,
  drawing: Object.freeze({ iconKind: ENTRY_ICON_KIND.DXF }),
  robot: ROBOT_CAPABILITIES,
  // A KiCad board, the one plot (`packages/ui/src/renderers/board`).
  plot: Object.freeze({ iconKind: ENTRY_ICON_KIND.KICAD_PCB })
});

export const RENDER_CAPABILITIES = Object.freeze(Object.fromEntries(
  DOCUMENT_TYPE_REGISTRY.documentTypes.map((type) => [
    type.wire,
    type.view === "mesh" ? Object.freeze({ iconKind: MESH_ICONS[type.wire] }) : VIEW_CAPABILITIES[type.view] || DEFAULT_CAPABILITIES
  ])
));

// Extension aliases that name the same render format.
const FORMAT_ALIASES = Object.freeze({
  stp: RENDER_FORMAT.STEP,
  gltf: RENDER_FORMAT.GLB
});

// Capabilities for a render format. An unrecognised format gets the conservative default row.
export function renderCapabilities(renderFormat) {
  const normalized = normalizeFormat(renderFormat);
  const resolved = FORMAT_ALIASES[normalized] || normalized;
  return RENDER_CAPABILITIES[resolved] || DEFAULT_CAPABILITIES;
}

export function entryIconKindForRenderFormat(renderFormat) {
  return renderCapabilities(renderFormat).iconKind;
}
