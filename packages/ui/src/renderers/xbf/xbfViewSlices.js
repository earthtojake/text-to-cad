// An engine document's own slices of the file's view (`kit/shell/fileView.js`), as a STEP's were
// before the migration (its `stepViewSlices.js`): what the person left it looking at and posed to.
// The shell keeps the camera and the Display settings; everything here is the xbf renderer's alone,
// and it is view state only -- never the selection, the tool or a measurement, which every open
// starts afresh.
//
//   tree   { expanded, hidden, isolated }   against the document's tree: its assemblies and instances
//   pose   { preset, given, couplings }     against its mechanism: its pairs, configurations, couplings
//   pmi    { hidden, off }                  against the parts its PMI is on: the annotations hidden, and all of them
//
// `expanded` are the Model tree's open rows (selection ids; a folded group's own row id), `hidden` the
// instances hidden (`i3`),
// `isolated` the nodes isolated; `preset` is the Pose row's choice (a configuration, Default or
// Custom), `given` the values set by hand and `couplings` each coupling's slider (`useXbfPose`);
// `hidden` the PMI hidden, each by its part and its author's id (`pmiKey`: `0:top-flat`, an id being
// unique only on its part), and `off` whether the PMI is hidden whole.
//
// A slice comes back only when the document it was written against is still the one on screen: a
// rebuild that changed the parts renumbers the instances (`i3` is an index), so ids from the old one
// are not ids at all, and one that changed the mechanism may not have the joints the pose names. The
// shell applies that rule from the signatures below; this module says what each slice holds.

const text = value => String(value ?? "").trim();
const plainObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const idList = value => (Array.isArray(value) ? [...new Set(value.map(text).filter(Boolean))] : []);

// A short digest of what a slice is written against (FNV-1a, 32 bits): a signature, not a key to look
// anything up by, so a collision only ever keeps a slice it should have dropped.
function digest(value) {
  let hash = 0x811c9dc5;
  for (let at = 0; at < value.length; at += 1) {
    hash ^= value.charCodeAt(at);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

/**
 * What each slice is written against: the tree the document's structure has (its tree and its
 * instances, each by its path and prototype), the mechanism its kinematics has (`useXbfPose`'s
 * key: the pairs, the configurations, the as-built values and the couplings), and the parts its PMI
 * is on (its prototypes, by name: a hidden annotation is its part's number and its author's id, so a
 * rebuild of the same parts keeps it, whatever it changed of them). No structure, no signatures:
 * nothing can come back yet. A document with no mechanism has no pose to keep, one with no PMI none.
 * @param {object | null} structure  The engine's structure (`scene.structure`).
 * @param {object | null} kinematics  The scene's kinematics (`scene.kinematics`).
 * @returns {{ tree: string, pose?: string, pmi?: string } | null}
 */
export function xbfViewSignatures(structure, kinematics) {
  if (!structure) return null;
  const tree = digest(JSON.stringify([structure.tree ?? null,
    (structure.instances || []).map(instance => [instance.path ?? null, instance.prototype ?? null])]));
  const signatures = { tree };
  if (kinematics) signatures.pose = digest(JSON.stringify([kinematics.pairs, kinematics.configurations, kinematics.asBuilt, kinematics.couplings || null]));
  if (Array.isArray(structure.pmi) && structure.pmi.length) signatures.pmi = digest(JSON.stringify((structure.prototypes || []).map(prototype => prototype?.name ?? null)));
  return signatures;
}

export const NO_TREE = Object.freeze({ expanded: Object.freeze([]), hidden: Object.freeze([]), isolated: Object.freeze([]) });

function readTree(value) {
  if (!plainObject(value)) return null;
  return { expanded: idList(value.expanded), hidden: idList(value.hidden), isolated: idList(value.isolated) };
}

function readPose(value) {
  if (!plainObject(value)) return null;
  const numbers = entry => (Array.isArray(entry) ? entry.every(Number.isFinite) : Number.isFinite(entry));
  const values = record => (plainObject(record) && Object.values(record).every(numbers) ? structuredClone(record) : null);
  return {
    preset: text(value.preset) || null,
    given: values(value.given),
    couplings: values(value.couplings)
  };
}

function readPmi(value) {
  if (!plainObject(value)) return null;
  return { hidden: idList(value.hidden), off: value.off === true };
}

/**
 * The slices as the renderer restores them, from what the shell handed back for this document
 * (`readFileView(raw, signatures).renderer`): the tree always (empty when it did not come back), the
 * pose where one came back.
 * @param {Record<string, unknown>} renderer
 * @returns {{ tree: { expanded: string[], hidden: string[], isolated: string[] }, pose: { preset: string | null,
 *   given: Record<string, number | number[]> | null, couplings: Record<string, number> | null } | null,
 *   pmi?: { hidden: string[], off: boolean } }}  `pmi` where one came back.
 */
export function readXbfView(renderer) {
  const record = plainObject(renderer) ? renderer : {};
  const pmi = readPmi(record.pmi);
  return { tree: readTree(record.tree) || NO_TREE, pose: readPose(record.pose), ...(pmi ? { pmi } : {}) };
}

/**
 * The slices for the document on screen as it stands: its tree's state and, where it has a
 * mechanism, Position's pose.
 * @param {{ tree: { expanded?: string[], hidden?: string[], isolated?: string[] }, pose?: object | null,
 *   pmi?: { hidden?: string[], off?: boolean } | null }} state
 */
export function xbfViewSlices({ tree, pose = null, pmi = null }) {
  const slices = { tree: readTree(tree) || { ...NO_TREE } };
  if (pose) slices.pose = readPose(pose);
  if (pmi) slices.pmi = readPmi(pmi);
  return slices;
}
