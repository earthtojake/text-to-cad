import { entryHasMesh } from "@text-to-cad/core/lib/entryAssets.js";
import { canonicalJson } from "./canonicalJson.js";

// A build's preview revision as the surface draws it (STORE.md 9b): entry-shaped, so it is read
// exactly as a saved file's catalog row is -- its tree's view at `url`, each component's part by
// its key, its articulation, routines and finishes inline -- and never the catalog's entry
// (`preview: true`; nothing binds the file's sidecar to it, and no snapshot or export reads it).

// What a catalog row carries of a file's sidecar, which a preview's annotations carry for it.
const MOTION_FIELDS = Object.freeze(["articulation", "poseUrl", "animation", "tubeSkinsUrl"]);
const FINISH_FIELDS = Object.freeze(["display", "appearanceHash"]);

function fields(entry, names) {
  return Object.fromEntries(names.filter(name => entry?.[name] !== undefined).map(name => [name, entry[name]]));
}

/** Whether a routine of `animation` bends a tube, which only the saved document's skins draw. */
export function bendsATube(animation) {
  return (Array.isArray(animation?.clips) ? animation.clips : [])
    .some(clip => (Array.isArray(clip?.tracks) ? clip.tracks : []).some(track => track?.tube != null));
}

// The preview's own motion: its articulation, versioned by the object it came in, and its routines.
// A routine that bends a tube plays the saved document's skins, which a preview has none of: it
// plays on the preview only as the routine in hand, with that document's skins, when its keyframes
// are the same -- else it waits for the save.
function annotationMotion(annotations, preview, carried) {
  const motion = {};
  if (annotations.articulation) {
    motion.articulation = annotations.articulation;
    motion.poseUrl = `preview:${preview.annotations}`;
  }
  if (annotations.animation) {
    if (!bendsATube(annotations.animation)) motion.animation = annotations.animation;
    else if (carried?.animation && carried.tubeSkinsUrl && canonicalJson(carried.animation) === canonicalJson(annotations.animation)) {
      motion.animation = carried.animation;
      motion.tubeSkinsUrl = carried.tubeSkinsUrl;
    }
  }
  return motion;
}

// The preview's own finishes, per occurrence, as the scanner lists a saved file's. Finishes the
// same as the ones in hand keep their token: the composition stays as it is.
function annotationFinishes(annotations, preview, carried) {
  if (annotations.appearance === null || annotations.appearance === undefined) return {};
  const display = annotations.display && typeof annotations.display === "object" ? annotations.display : {};
  const same = carried?.display && carried.appearanceHash && canonicalJson(carried.display) === canonicalJson(display);
  return { display, appearanceHash: same ? carried.appearanceHash : `preview:${preview.annotations}` };
}

/**
 * The preview revision `preview` (the feed's, `editingPreview.js`) as an entry: null until its
 * view is read. `view` is the tree's `assembly.json`, whose `entryKind` is the kind the scanner
 * lists; `url` where the view was read (`storeTreeUrl`); `annotations` the object bound to the
 * preview (`previewAnnotationsFor`), or null until it is named and read.
 *
 * `inHand` is the catalog's entry on screen when the build began. While the build may still resolve
 * its declarations (`pending`), what is in hand stays in hand -- the articulation, the routines, the
 * finishes, by the tokens the two revisions share -- as a rebuild keeps the kinematics in hand until
 * its new ones arrive (the Position rule). Once the preview's own annotations bind, its finishes
 * bind only when `dressed`: the preview's geometry is on screen whole, since a change of finishes
 * reloads the composition, and a load cancelled part way would drop what it drew.
 */
export function previewRevisionEntry({ file, preview, view, url, annotations = null, inHand = null, pending = false, dressed = true }) {
  const path = String(file || "").trim();
  if (!path || !preview?.tree || !view || !url) return null;
  const carried = inHand && String(inHand.file || "").trim() === path && entryHasMesh(inHand) ? inHand : null;
  const entry = { file: path, kind: view.entryKind === "assembly" ? "assembly" : "part", url, hash: preview.tree, preview: true };
  if (annotations) {
    Object.assign(entry, annotationMotion(annotations, preview, carried));
    Object.assign(entry, dressed ? annotationFinishes(annotations, preview, carried) : fields(carried, FINISH_FIELDS));
  } else if (pending) {
    Object.assign(entry, fields(carried, MOTION_FIELDS), fields(carried, FINISH_FIELDS));
  }
  return entry;
}

function abortError() {
  return typeof DOMException === "function"
    ? new DOMException("The operation was aborted.", "AbortError")
    : Object.assign(new Error("The operation was aborted."), { name: "AbortError" });
}

/**
 * The parts a preview's build has named so far, as its mesh load waits on them: a component the
 * feed has not named yet is coming (the build is deriving its part), so the load draws what is
 * named and waits here instead of asking cadgen for it. `update` is every feed answer; `whenNamed`
 * settles once the part is named, or once the build has named all it can (`complete`), after which
 * an unnamed component is a saved file's missing part; it rejects when the load is abandoned.
 */
export function createPreviewPartsGate(tree) {
  const named = new Set();
  const waiters = new Set();
  let complete = false;
  const settle = () => { for (const check of [...waiters]) check(); };
  return {
    tree,
    get complete() { return complete; },
    has: cid => named.has(String(cid)),
    update(parts, isComplete) {
      for (const cid of Object.keys(parts || {})) named.add(String(cid));
      complete = isComplete === true;
      settle();
    },
    whenNamed(cid, signal) {
      return new Promise((resolve, reject) => {
        const key = String(cid);
        const abort = () => { waiters.delete(check); reject(abortError()); };
        function check() {
          if (!named.has(key) && !complete) return;
          waiters.delete(check);
          signal?.removeEventListener("abort", abort);
          resolve();
        }
        if (signal?.aborted) { reject(abortError()); return; }
        waiters.add(check);
        signal?.addEventListener("abort", abort, { once: true });
        check();
      });
    },
  };
}
