/**
 * Shortest unique path suffix (SUFP) — the compact way to say which file a ref belongs to.
 *
 * A ref copied out of the viewer should survive being pasted into a prompt that spans several
 * files, and `models/step/assemblies/motorcycle_shock_absorber.step.py#o1.1.2` is too long to
 * put in front of every ref. The shortest trailing run of path segments that names exactly one
 * entry is almost always just the filename.
 *
 * A `.step.py` generator shows as a bare stem — `bracket.step.py` is just `bracket` — because
 * generators are what people actually work in, so the common case gets the shortest name. A raw
 * `bracket.step` keeps its suffix, which is what tells the two apart.
 *
 * Meshes and drawings keep their extension too, and that is what makes the stripping safe:
 * `mounting_plate` (the generator) and `mounting_plate.stl` stay distinct. Stripping extensions
 * from EVERYTHING would collide 71 of 315 names in this repo; this scheme collides 6 of 407,
 * exactly the same three filenames as keeping them in full.
 *
 * The cost is that a bare displayed name is NOT a literal path suffix, so resolving one back to
 * a file means expanding it (`bracket` -> `bracket.step.py`) rather than matching verbatim.
 * cadgen.cad_ref_syntax owns that expansion, since the CLI guard is its only caller.
 *
 * Emission is allowed to drift: adding a file that collides lengthens another entry's suffix.
 * Acceptance is not, which is why resolvers match any unambiguous suffix rather than only the
 * shortest one.
 */

/** Split a path into segments, tolerating Windows separators and duplicate slashes. */
function segmentsOf(path) {
  return String(path || "")
    .replace(/\\/g, "/")
    .split("/")
    .filter(Boolean);
}

// Only the generator suffix is stripped. `.step`, `.stp`, `.stl`, `.3mf`, `.glb` and `.dxf`
// all keep theirs -- for meshes because the extension is what identifies them, and for raw
// STEP because it is what distinguishes `bracket.step` from the `bracket.step.py` that builds
// it.
const GENERATOR_SUFFIXES = [".step.py", ".stp.py"];

/** The name a ref shows: `bracket.step.py` -> `bracket`; every other file keeps its suffix. */
export function refDisplayName(fileName) {
  const name = String(fileName || "").trim();
  for (const suffix of GENERATOR_SUFFIXES) {
    if (name.toLowerCase().endsWith(suffix)) {
      return name.slice(0, name.length - suffix.length);
    }
  }
  return name;
}

/** A path with its final segment reduced to the displayed name. */
function displayPath(path) {
  const segments = segmentsOf(path);
  if (!segments.length) {
    return "";
  }
  segments[segments.length - 1] = refDisplayName(segments[segments.length - 1]);
  return segments.join("/");
}

/**
 * Map every path to its shortest unique trailing-segment run.
 *
 * Comparison is always segment-aligned: `late.stl` is NOT a suffix of `mounting_plate.stl`,
 * because suffix matching on raw strings would make refs resolve to the wrong file.
 */
export function shortestUniquePathSuffixes(paths) {
  // Keyed by the ORIGINAL path, computed over the DISPLAY form: the suffix a user sees and
  // pastes is the thing that has to be unique.
  const originalByDisplay = new Map();
  const cleaned = [];
  const seen = new Set();
  for (const path of Array.isArray(paths) ? paths : []) {
    const normalized = segmentsOf(path).join("/");
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    const shown = displayPath(normalized);
    cleaned.push(shown);
    if (!originalByDisplay.has(shown)) {
      originalByDisplay.set(shown, normalized);
    }
  }

  // suffixCounts.get(k) tells how many paths end in a given k-segment run, so uniqueness is a
  // lookup rather than a rescan per candidate.
  const suffixCounts = new Map();
  const longest = cleaned.reduce((max, path) => Math.max(max, segmentsOf(path).length), 0);
  for (let k = 1; k <= longest; k += 1) {
    const counts = new Map();
    for (const path of cleaned) {
      const segments = segmentsOf(path);
      if (segments.length < k) {
        continue;
      }
      const candidate = segments.slice(segments.length - k).join("/");
      counts.set(candidate, (counts.get(candidate) || 0) + 1);
    }
    suffixCounts.set(k, counts);
  }

  const result = new Map();
  for (const path of cleaned) {
    const segments = segmentsOf(path);
    let suffix = path;
    for (let k = 1; k <= segments.length; k += 1) {
      const candidate = segments.slice(segments.length - k).join("/");
      if ((suffixCounts.get(k)?.get(candidate) || 0) === 1) {
        suffix = candidate;
        break;
      }
    }
    result.set(originalByDisplay.get(path) || path, suffix);
  }
  return result;
}
