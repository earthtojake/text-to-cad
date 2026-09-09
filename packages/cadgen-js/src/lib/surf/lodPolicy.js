// Viewport LOD policy (design/unified-tessellation.md Phase 5).
//
// Pure math, no three.js, no DOM: given a camera sample and a component's
// bounds, decide which chord-tolerance level the component SHOULD render at,
// with an enter/exit hysteresis band so orbiting across a boundary never
// thrashes the tessellator. The scheduler (viewer-side) owns time — debounce,
// in-flight limits, cancellation — this module owns only the geometry.

// Chord-tolerance ladder, relative to the component diagonal. Index 0 is the
// tessellator default every component loads at; higher indices are finer.
// angleTolerance stays at the tessellator default for every level: angular
// error is scale-free, so zoom starves only the chord criterion.
export const LOD_CHORD_LEVELS = [1.5e-3, 5e-4, 1.5e-4];

// The band: a component upgrades when its current level projects worse than
// UPGRADE_PX, and downgrades only when the coarser level would still sit
// under DOWNGRADE_PX. TARGET_PX picks the desired level from scratch.
export const LOD_TARGET_PX = 1.0;
export const LOD_UPGRADE_PX = 1.25;
export const LOD_DOWNGRADE_PX = 0.6;

/**
 * Screen-space pixels per world unit at distance `d`.
 *
 * camera: { kind: "perspective", fovYDeg } | { kind: "orthographic", visibleWorldHeight }
 */
export function pixelsPerUnit(camera, distance, viewportHeightPx) {
  if (!(viewportHeightPx > 0)) {
    return 0;
  }
  if (camera.kind === "orthographic") {
    const height = Number(camera.visibleWorldHeight);
    return height > 0 ? viewportHeightPx / height : 0;
  }
  const fovY = (Number(camera.fovYDeg) * Math.PI) / 180;
  if (!(fovY > 0) || !(distance > 0)) {
    return 0;
  }
  return viewportHeightPx / (2 * distance * Math.tan(fovY / 2));
}

/**
 * Worst-case projected silhouette error, in pixels, of tessellating a
 * component of bounding `diagonal` at relative chord tolerance `chordRel`,
 * seen from `cameraDistance` to the component's bbox CENTER. The distance is
 * reduced by the bounding radius (and floored at a hundredth of the radius):
 * a camera inside or right at a part demands its finest level.
 */
export function projectedChordErrorPx({
  chordRel,
  diagonal,
  cameraDistance,
  camera,
  viewportHeightPx,
}) {
  const radius = diagonal / 2;
  const nearest = Math.max(cameraDistance - radius, radius * 0.01);
  const pxPerUnit = pixelsPerUnit(camera, nearest, viewportHeightPx);
  return chordRel * diagonal * pxPerUnit;
}

/** The coarsest level whose projected error meets the target. */
export function desiredLevel(sample, levels = LOD_CHORD_LEVELS, targetPx = LOD_TARGET_PX) {
  for (let level = 0; level < levels.length; level += 1) {
    const errorPx = projectedChordErrorPx({ ...sample, chordRel: levels[level] });
    if (errorPx <= targetPx) {
      return level;
    }
  }
  return levels.length - 1;
}

/**
 * The level to render next, given the current one — the hysteresis step.
 * Moves at most one level per call (the scheduler re-evaluates after each
 * swap, so sustained zoom still climbs the whole ladder).
 */
export function nextLevel(sample, currentLevel, levels = LOD_CHORD_LEVELS) {
  const current = Math.max(0, Math.min(levels.length - 1, currentLevel | 0));
  const currentErrorPx = projectedChordErrorPx({ ...sample, chordRel: levels[current] });
  if (currentErrorPx > LOD_UPGRADE_PX && current < levels.length - 1) {
    return current + 1;
  }
  if (current > 0) {
    const coarserErrorPx = projectedChordErrorPx({ ...sample, chordRel: levels[current - 1] });
    if (coarserErrorPx < LOD_DOWNGRADE_PX) {
      return current - 1;
    }
  }
  return current;
}

/**
 * Rank upgrade work, worst projected error first, so the nearest/largest
 * components on screen re-tessellate before distant specks. Entries:
 * { cid, currentLevel, sample } -> [{ cid, level, errorPx }] for entries whose
 * next level differs from the current one.
 */
export function planLodWork(entries, levels = LOD_CHORD_LEVELS) {
  const plan = [];
  for (const { cid, currentLevel, sample } of entries) {
    const level = nextLevel(sample, currentLevel, levels);
    if (level === currentLevel) {
      continue;
    }
    plan.push({
      cid,
      level,
      errorPx: projectedChordErrorPx({ ...sample, chordRel: levels[currentLevel] }),
    });
  }
  // Upgrades (positive error pressure) first, ordered worst-first; downgrades
  // trail — they only reclaim memory, never fix a visible artifact.
  plan.sort((a, b) => b.errorPx - a.errorPx);
  return plan;
}
