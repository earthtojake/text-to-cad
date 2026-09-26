import { entryAssetHash } from "@hardcore/core/lib/entryAssets.js";

// The STEP renderer's own slot in the shell's per-file record (`kit/shell/shellState.js`):
// what it was left looking at, posed to, and playing. The shell keeps the camera, the
// Display settings and the tool; everything here is a STEP's alone.
//
//   { tree, treeSignature, pose, animation, motionSignature, largeFile, largeFileSignature }
//
// A slice comes back only when the file it was written against is still the file on
// screen. That is what the signatures are: a rebuilt model has different topology, so a
// selection of face ids from the old one is not a selection at all, and a sidecar that was
// regenerated may not have the parameters the stored pose names. Reading is forgiving
// (a slice that does not match is simply absent); writing is exact.

const text = value => String(value ?? "").trim();
const plainObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const idList = value => (Array.isArray(value) ? [...new Set(value.map(text).filter(Boolean))] : []);
const bool = (value, fallback = false) => (typeof value === "boolean" ? value : fallback);
const num = (value, fallback = 0) => (Number.isFinite(Number(value)) ? Number(value) : fallback);

/**
 * What each slice was written against. The tree and the large-file decision both turn on
 * the model's geometry and topology; the pose and the routine both come out of the one
 * sidecar, so a rebuilt sidecar invalidates both together.
 */
export function stepRecordSignatures(entry) {
  const geometry = [
    text(entry?.kind).toLowerCase(), text(entry?.hash),
    entryAssetHash(entry, "selectorTopology"), entryAssetHash(entry, "topology"), entryAssetHash(entry, "glb")
  ].filter(Boolean).join(":") || text(entry?.file);
  return { geometry, motion: [entryAssetHash(entry, "stepModule"), text(entry?.hash)].filter(Boolean).join(":") };
}

const NO_TREE = Object.freeze({
  selectedReferenceIds: [], selectedPartIds: [], expandedStepTreeNodeIds: [], hiddenPartIds: []
});

function readTree(value) {
  if (!plainObject(value)) return null;
  return {
    selectedReferenceIds: idList(value.selectedReferenceIds),
    selectedPartIds: idList(value.selectedPartIds),
    expandedStepTreeNodeIds: idList(value.expandedStepTreeNodeIds),
    hiddenPartIds: idList(value.hiddenPartIds)
  };
}

function readAnimation(value) {
  if (!plainObject(value)) return null;
  return {
    activeClipId: text(value.activeClipId), enabled: bool(value.enabled, true),
    elapsedSec: Math.max(0, num(value.elapsedSec)), speed: num(value.speed, 1) > 0 ? num(value.speed, 1) : 1,
    loopEnabled: bool(value.loopEnabled, true)
  };
}

/**
 * The record as it applies to the entry on screen now. Every field is always present: a
 * slice whose signature no longer matches comes back as its default, never as the stale one.
 *
 * @param {object} renderer  `readShellState(view.state).renderer`.
 * @param {{ geometry: string, motion: string }} signatures  For the entry on screen.
 */
export function readStepRecord(renderer, signatures) {
  const record = plainObject(renderer) ? renderer : {};
  const matches = (stored, current) => Boolean(current) && text(stored) === current;
  const geometryMatches = matches(record.treeSignature, signatures.geometry);
  return {
    tree: (geometryMatches && readTree(record.tree)) || NO_TREE,
    pose: (matches(record.motionSignature, signatures.motion) && plainObject(record.pose?.parameterValues)
      ? { parameterValues: { ...record.pose.parameterValues } } : null),
    animation: (matches(record.motionSignature, signatures.motion) && readAnimation(record.animation)) || null,
    largeFile: { selectableTopologyEnabled: matches(record.largeFileSignature, signatures.geometry)
      && bool(record.largeFile?.selectableTopologyEnabled, false) }
  };
}

/** The record for the STEP on screen as it is now, signatures included. */
export function writeStepRecord({ tree, pose, animation, largeFile, signatures }) {
  return {
    tree: readTree(tree) || NO_TREE, treeSignature: signatures.geometry,
    pose: { parameterValues: plainObject(pose?.parameterValues) ? { ...pose.parameterValues } : {} },
    animation: readAnimation(animation) || readAnimation({}),
    motionSignature: signatures.motion,
    largeFile: { selectableTopologyEnabled: bool(largeFile?.selectableTopologyEnabled, false) },
    largeFileSignature: signatures.geometry
  };
}

/**
 * What the record is written from, the surface as it stands: its tree, its Position values,
 * its routine (while a clip plays, the time is the clock's: React state holds where it last
 * paused) and its large-file choice.
 */
export function stepRecordInputs({ tree, parameterValues, animationState, clockTime, largeFileState, signatures }) {
  return {
    tree,
    pose: { parameterValues },
    animation: {
      activeClipId: animationState.activeClipId, enabled: animationState.enabled,
      elapsedSec: animationState.playing ? clockTime() : animationState.elapsedSec,
      speed: animationState.speed, loopEnabled: animationState.loopEnabled
    },
    largeFile: { selectableTopologyEnabled: largeFileState.selectableTopologyEnabled },
    signatures
  };
}

/**
 * The Position values a restored record starts from, or null when it has no pose slice. A
 * routine that owned the pose wins outright: the losing owner's raw values are not restored.
 */
export function restoredPoseValues(restored) {
  if (!restored.pose) return null;
  return restored.animation?.enabled !== false && restored.animation?.activeClipId ? {} : restored.pose.parameterValues;
}
