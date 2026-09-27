import { entryAssetHash } from "@hardcore/core/lib/entryAssets.js";

// The STEP renderer's own slices of the file's view (`kit/shell/fileView.js`): what it was
// left looking at and posed to. The shell keeps the camera and the Display settings;
// everything here is a STEP's alone, and it is view state only — never the selection, the
// tool, a measurement or a routine's time, which every open starts afresh.
//
//   tree       { expandedStepTreeNodeIds, hiddenPartIds, isolatedAssemblyNodeIds }   against the geometry
//   pose       { parameterValues }                                                     against the motion sidecar
//   largeFile  { selectableTopologyEnabled }                                           against the geometry
//
// A slice comes back only when the file it was written against is still the file on screen:
// a rebuilt model has different topology, so node ids from the old one are not ids at all,
// and a regenerated sidecar may not have the parameters the stored pose names. The shell
// applies that rule from the signatures below; this module says what each slice holds.

const text = value => String(value ?? "").trim();
const plainObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const idList = value => (Array.isArray(value) ? [...new Set(value.map(text).filter(Boolean))] : []);

/**
 * What each slice is written against. The tree and the large-file decision both turn on the
 * model's geometry and topology; the pose comes out of the sidecar, so a rebuilt sidecar
 * invalidates it.
 * @returns {{ tree: string, pose: string, largeFile: string }}
 */
export function stepViewSignatures(entry) {
  const geometry = [
    text(entry?.kind).toLowerCase(), text(entry?.hash),
    entryAssetHash(entry, "selectorTopology"), entryAssetHash(entry, "topology"), entryAssetHash(entry, "glb")
  ].filter(Boolean).join(":") || text(entry?.file);
  const motion = [entryAssetHash(entry, "stepModule"), text(entry?.hash)].filter(Boolean).join(":");
  return { tree: geometry, pose: motion, largeFile: geometry };
}

export const NO_TREE = Object.freeze({ expandedStepTreeNodeIds: [], hiddenPartIds: [], isolatedAssemblyNodeIds: [] });

function readTree(value) {
  if (!plainObject(value)) return null;
  return {
    expandedStepTreeNodeIds: idList(value.expandedStepTreeNodeIds),
    hiddenPartIds: idList(value.hiddenPartIds),
    isolatedAssemblyNodeIds: idList(value.isolatedAssemblyNodeIds)
  };
}

/**
 * The slices as the surface restores them, from what the shell handed back for this file
 * (`readFileView(raw, signatures).renderer`): every field always present, a slice that was
 * not restored as its default.
 * @param {Record<string, unknown>} renderer
 */
export function readStepView(renderer) {
  const record = plainObject(renderer) ? renderer : {};
  return {
    tree: readTree(record.tree) || NO_TREE,
    pose: plainObject(record.pose?.parameterValues) ? { parameterValues: { ...record.pose.parameterValues } } : null,
    largeFile: { selectableTopologyEnabled: record.largeFile?.selectableTopologyEnabled === true }
  };
}

/** The slices for the STEP on screen as it stands: its tree, its Position values and its large-file choice. */
export function stepViewSlices({ tree, parameterValues, largeFileState }) {
  return {
    tree: readTree(tree) || NO_TREE,
    pose: { parameterValues: plainObject(parameterValues) ? { ...parameterValues } : {} },
    largeFile: { selectableTopologyEnabled: largeFileState?.selectableTopologyEnabled === true }
  };
}
