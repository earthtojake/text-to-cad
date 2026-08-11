import { normalizeFormat } from "cadjs/lib/fileFormats.js";
import {
  entryIconKindForRenderFormat,
  ENTRY_ICON_KIND
} from "cadjs/lib/renderCapabilities.js";

export { ENTRY_ICON_KIND };

// Whether an entry's geometry is produced by running a generator script — a
// `.step.py` or `.dxf.py`, or a catalog entry marked sourceKind "python".
//
// This does NOT change which icon the entry gets: a generated model shows the
// same icon as the imported file it stands in for, so a `.step.py` assembly and
// an imported `.step` assembly read alike in the file list. Being code-derived
// is carried by the small badge in the icon's bottom-right corner instead.
//
// An `.implicit.js` is not included: it is not generated FROM code, it IS the
// code, so it keeps its own icon and takes no badge.
export function isCodeDerivedEntry(entry) {
  if (String(entry?.sourceKind || "").trim().toLowerCase() === "python") {
    return true;
  }
  const sourcePath = String(
    entry?.source?.sourcePath || entry?.source?.file || entry?.file || ""
  ).toLowerCase();
  return sourcePath.endsWith(".step.py") || sourcePath.endsWith(".dxf.py");
}

// An entry names its format twice — the catalog's `kind` and the resolved source format —
// and they can disagree (an `.srdf` entry whose source format resolves to the robot family,
// a `.gltf` that normalizes to GLB). The old cascade tested BOTH at every rung, so the
// rung's position silently decided which won. Keep that resolution order, but state it once
// as data instead of re-deriving it from eight format comparisons.
const ICON_KIND_PRECEDENCE = [
  ENTRY_ICON_KIND.DXF,
  ENTRY_ICON_KIND.IMPLICIT,
  ENTRY_ICON_KIND.ROBOT,
  ENTRY_ICON_KIND.STL_MESH,
  ENTRY_ICON_KIND.THREE_MF_MESH,
  ENTRY_ICON_KIND.GLB_MESH,
  // STEP family: one icon for the format. Part vs assembly is structure, not file type,
  // and the tree already shows it. Generated and imported share it too; the code badge
  // carries that difference. Also the fallback for anything unrecognised.
  ENTRY_ICON_KIND.STEP
];

export function entryIconKind(entry, {
  sourceFormat = "",
  status = {}
} = {}) {
  const safeStatus = status || {};
  if (safeStatus.artifactGenerating || safeStatus.loading) {
    return ENTRY_ICON_KIND.LOADING;
  }

  const normalizedKind = normalizeFormat(entry?.kind);
  const candidates = new Set([
    entryIconKindForRenderFormat(normalizeFormat(sourceFormat || entry?.kind)),
    entryIconKindForRenderFormat(normalizedKind)
  ]);
  // An `.srdf` catalog kind is not a render format of its own in every catalog payload,
  // so it names the robot icon directly.
  if (normalizedKind === "srdf") {
    candidates.add(ENTRY_ICON_KIND.ROBOT);
  }

  return ICON_KIND_PRECEDENCE.find((iconKind) => candidates.has(iconKind)) || ENTRY_ICON_KIND.STEP;
}
