import { RENDER_FORMAT, normalizeFormat } from "./fileFormats.js";

// WHAT EACH RENDER FORMAT CAN DO — one table, so viewer code asks "can this format
// do X?" instead of "is this format Y?".
//
// Every identity check spread through the client (`renderFormat === RENDER_FORMAT.DXF`,
// `isMeshRenderFormat(...)`, the `xxxMode` boolean piles) is a place a new format has to
// be hand-added and a place an improvement fails to reach the other formats. That is not
// hypothetical: the Orbit button was gated off for implicit and for DXF independently and
// had to be fixed twice, and implicit grew a whole parallel export route to an endpoint
// the server does not implement. Both were "this format was not on the list" bugs.
//
// So: a format is a ROW here plus a render backend (see viewer/docs/render-types.md).
// Shared behaviour lives in the viewer shell and reads this table; it is never re-derived
// from the format's identity.
//
// Rules for changing this file:
// - Add a capability when the SECOND format needs it, never speculatively.
// - Capabilities are DATA. No behaviour, no imports beyond the format enum.
// - Format-specific *content* (STEP's tree, DXF's bends, an implicit's graphics tab)
//   stays format-specific — the flags below decide WHICH panels mount, not what is in
//   them.

// Which loaded object is "the thing on screen" for this format. The viewer resolves it
// once into a single content signal; asking `!selectedMeshData` is what left implicit's
// screenshot and orbit buttons permanently disabled, since a raymarched model never
// loads a mesh.
export const VIEWPORT_CONTENT = Object.freeze({
  MESH: "mesh",
  IMPLICIT: "implicit",
  ROBOT: "robot"
});

// How parameters reach the viewer: from a sibling `.step.js` sidecar module, or declared
// inside the `.implicit.js` model itself. Different stores, one consumer surface.
export const PARAMETER_SOURCE = Object.freeze({
  SIDECAR: "sidecar",
  MODULE: "module"
});

// WHICH ASSET the viewer loads for this format — not the same question as `content`, which
// is what ends up drawn. A DXF loads a DRAWING and renders it as a mesh, so it shares the
// mesh viewport but not the mesh loader, and every "is it loaded yet?" check has to ask
// about the drawing. Loader implementations stay per-format; this only names which one.
export const ASSET_KIND = Object.freeze({
  MESH: "mesh",
  DRAWING: "drawing",
  IMPLICIT: "implicit",
  ROBOT: "robot"
});

// The file-list glyph. A table rather than a cascade of format tests: the icon is the most
// purely per-format fact in the client, and it was the longest identity cascade.
export const ENTRY_ICON_KIND = Object.freeze({
  LOADING: "loading",
  DXF: "dxf",
  IMPLICIT: "implicit",
  ROBOT: "robot",
  STEP: "step",
  STL_MESH: "stl-mesh",
  THREE_MF_MESH: "3mf-mesh",
  GLB_MESH: "glb-mesh"
});

// The toolbar cluster. ALL of these act on the VIEWPORT, not on the geometry, so every
// format gets every one of them — a mesh can be panned and annotated exactly as a STEP
// assembly can. Select is the only one that needs a caveat: on a format without `topology`
// it is inert, and stays visible so the toolbar keeps one shape rather than reflowing as
// you move between files.
//
// Kept as a map rather than dropped now that every row agrees, because this is the place a
// format would DECLINE a tool, and because the shell reads it through `supportsTool`. A
// row that overrides it is making a claim; today none do.
const VIEWPORT_TOOLS = Object.freeze({
  select: true,
  pan: true,
  draw: true,
  orbit: true,
  screenshot: true
});

const MESH_CAPABILITIES = Object.freeze({
  content: VIEWPORT_CONTENT.MESH,
  assetKind: ASSET_KIND.MESH,
  iconKind: ENTRY_ICON_KIND.STL_MESH,
  sheetKind: "mesh",
  label: "STL",
  parts: false,
  topology: false,
  // Triangle-corner Measure only. Not B-rep topology.
  measure: true,
  exploded: false,
  displayModes: false,
  clip: false,
  planView: false,
  themeProjection: true,
  params: null,
  animations: false,
  artifactManaged: false,
  exportFormats: Object.freeze([])
});

const ROBOT_CAPABILITIES = Object.freeze({
  content: VIEWPORT_CONTENT.ROBOT,
  assetKind: ASSET_KIND.ROBOT,
  iconKind: ENTRY_ICON_KIND.ROBOT,
  sheetKind: RENDER_FORMAT.URDF,
  label: "URDF",
  sceneScale: "urdf",
  // No selection. A URDF is a link tree, so links CAN be made pickable — that was tried and
  // removed: selecting one gives you nothing to do with it. There is no copyable reference
  // for a link the way there is for a STEP face or occurrence, so the whole affordance was
  // a selection highlight and no payload. On every non-STEP format the select TOOL stays
  // visible and inert: it is the default mode, and in it the left button orbits and the
  // right button pans, which is all a robot needs.
  parts: false,
  topology: false,
  measure: false,
  exploded: false,
  displayModes: false,
  clip: false,
  planView: false,
  themeProjection: true,
  params: null,
  animations: false,
  posePicker: true,
  artifactManaged: false,
  exportFormats: Object.freeze([])
});

const DEFAULT_CAPABILITIES = Object.freeze({
  content: VIEWPORT_CONTENT.MESH,
  assetKind: ASSET_KIND.MESH,
  iconKind: ENTRY_ICON_KIND.STEP,
  sheetKind: "",
  label: "",
  sceneScale: "cad",
  tools: VIEWPORT_TOOLS,
  parts: false,
  topology: false,
  measure: false,
  exploded: false,
  displayModes: false,
  clip: false,
  planView: false,
  // Projection is a THEME trait. Every format honours it; only the implicit raymarcher
  // needed shader work to accept a parallel-ray camera.
  themeProjection: true,
  params: null,
  animations: false,
  posePicker: false,
  // Formats whose VIEWPORT CONTENT comes from a generated package, so the viewer checks
  // freshness and may block on a build.
  //
  // This is a SUBSET of `owns_entry` in viewer/server_py/artifact.py, not a mirror of it.
  // The server also owns implicit entries — it builds their packages for export and
  // snapshot — but an implicit renders live from its own GLSL, so the viewer must never
  // wait on that build. Anything listed here and NOT owned by the server blocks forever;
  // adding implicit here to "fix the drift" would block a format that has nothing to wait
  // for.
  artifactManaged: false,
  // The command that rebuilds this entry's assets by hand, shown on a build-failure card.
  // Empty for everything the viewer can rebuild itself or that IS its own asset — which is
  // every format but an imported STEP. Eight identity checks used to say that.
  rebuildCommand: "",
  exportFormats: Object.freeze([])
});

export const RENDER_CAPABILITIES = Object.freeze({
  [RENDER_FORMAT.STEP]: Object.freeze({
    ...DEFAULT_CAPABILITIES,
    iconKind: ENTRY_ICON_KIND.STEP,
    sheetKind: RENDER_FORMAT.STEP,
    label: "STEP",
    parts: true,
    topology: true,
    measure: true,
    exploded: true,
    displayModes: true,
    clip: true,
    params: PARAMETER_SOURCE.SIDECAR,
    animations: true,
    artifactManaged: true,
    rebuildCommand: "python -m cadgen.step_artifact_cli --repo-root . --step",
    exportFormats: Object.freeze(["step", "3mf", "stl", "glb"])
  }),
  [RENDER_FORMAT.STL]: Object.freeze({ ...DEFAULT_CAPABILITIES, ...MESH_CAPABILITIES, label: "STL" }),
  [RENDER_FORMAT.THREE_MF]: Object.freeze({
    ...DEFAULT_CAPABILITIES,
    ...MESH_CAPABILITIES,
    iconKind: ENTRY_ICON_KIND.THREE_MF_MESH,
    label: "3MF"
  }),
  [RENDER_FORMAT.GLB]: Object.freeze({
    ...DEFAULT_CAPABILITIES,
    ...MESH_CAPABILITIES,
    iconKind: ENTRY_ICON_KIND.GLB_MESH,
    label: "GLB"
  }),
  [RENDER_FORMAT.DXF]: Object.freeze({
    ...DEFAULT_CAPABILITIES,
    assetKind: ASSET_KIND.DRAWING,
    iconKind: ENTRY_ICON_KIND.DXF,
    sheetKind: RENDER_FORMAT.DXF,
    label: "DXF",
    planView: true,
    artifactManaged: true,
    exportFormats: Object.freeze(["dxf"])
  }),
  [RENDER_FORMAT.IMPLICIT]: Object.freeze({
    ...DEFAULT_CAPABILITIES,
    content: VIEWPORT_CONTENT.IMPLICIT,
    assetKind: ASSET_KIND.IMPLICIT,
    iconKind: ENTRY_ICON_KIND.IMPLICIT,
    sheetKind: RENDER_FORMAT.IMPLICIT,
    label: "Implicit",
    params: PARAMETER_SOURCE.MODULE,
    animations: true,
    // Rendered live from its own GLSL: there is no baked artifact to be stale, so an
    // implicit never blocks on a build and never shows a generating state.
    artifactManaged: false,
    exportFormats: Object.freeze(["stl", "glb", "3mf"])
  }),
  [RENDER_FORMAT.URDF]: Object.freeze({ ...DEFAULT_CAPABILITIES, ...ROBOT_CAPABILITIES, label: "URDF" }),
  [RENDER_FORMAT.SRDF]: Object.freeze({
    ...DEFAULT_CAPABILITIES,
    ...ROBOT_CAPABILITIES,
    sheetKind: RENDER_FORMAT.SRDF,
    label: "SRDF"
  }),
  [RENDER_FORMAT.SDF]: Object.freeze({
    ...DEFAULT_CAPABILITIES,
    ...ROBOT_CAPABILITIES,
    sheetKind: RENDER_FORMAT.SDF,
    label: "SDF"
  })
});

// Extension aliases that name the same render format.
const FORMAT_ALIASES = Object.freeze({
  stp: RENDER_FORMAT.STEP,
  gltf: RENDER_FORMAT.GLB
});

// Capabilities for a render format. An unrecognised format gets the conservative default
// row: it renders, and every optional capability is off.
//
// Deliberately NOT normalizeRenderFormat(), which resolves anything unknown to STEP. That
// is the right default when picking a loader, and exactly wrong here — it would hand an
// unrecognised entry STEP's full capability set (parts, topology, clip, artifact-managed
// gating) and fail open on every one of them.
export function renderCapabilities(renderFormat) {
  const normalized = normalizeFormat(renderFormat);
  const resolved = FORMAT_ALIASES[normalized] || normalized;
  return RENDER_CAPABILITIES[resolved] || DEFAULT_CAPABILITIES;
}

// `renderCapabilities(f).tools[tool]`, with the lookup and the missing-tool case handled.
export function supportsTool(renderFormat, tool) {
  return renderCapabilities(renderFormat).tools?.[tool] === true;
}

// Reads one boolean capability. Keeps call sites free of optional chaining and makes the
// policy ratchet's allowlist easy to describe: capability reads look like this.
export function hasCapability(renderFormat, capability) {
  return renderCapabilities(renderFormat)[capability] === true;
}

export function viewportContentKind(renderFormat) {
  return renderCapabilities(renderFormat).content;
}

// Which parameter store backs this format, or "" when it has no parameters. The viewer
// resolves it once into a single active parameter runtime, so copy/paste/reset are
// written once rather than once per store.
export function parameterSourceKind(renderFormat) {
  return renderCapabilities(renderFormat).params || "";
}

export function renderFormatLabel(renderFormat) {
  return renderCapabilities(renderFormat).label;
}

export function exportFormatsForRenderFormat(renderFormat) {
  return renderCapabilities(renderFormat).exportFormats;
}

export function isArtifactManagedFormat(renderFormat) {
  return renderCapabilities(renderFormat).artifactManaged === true;
}

export function assetKindForRenderFormat(renderFormat) {
  return renderCapabilities(renderFormat).assetKind;
}

export function entryIconKindForRenderFormat(renderFormat) {
  return renderCapabilities(renderFormat).iconKind;
}

// The manual rebuild command for an entry, or "" when there is nothing to run by hand.
export function rebuildCommandForEntry(renderFormat, fileRef) {
  const command = String(renderCapabilities(renderFormat).rebuildCommand || "").trim();
  const ref = String(fileRef || "").trim();
  return command && ref ? `${command} ${ref}` : "";
}
