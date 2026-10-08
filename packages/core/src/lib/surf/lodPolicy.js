// Viewport LOD policy (design/unified-tessellation.md Phase 5).
//
// Pure math, no three.js, no DOM: given a camera sample and a component's
// bounds, decide which chord-tolerance level the component SHOULD render at,
// with an enter/exit hysteresis band so orbiting across a boundary never
// thrashes the tessellator. The scheduler (viewer-side) owns time — debounce,
// in-flight limits, cancellation — this module owns only the geometry.

// The tessellation ladder is cadgen's (cadgen.tessellation_policy): which rungs exist,
// coarse to fine, what chord (RELATIVE to a component's bounding diagonal) and angle
// (radians) tolerances each means, and which one every model opens at. It arrives with
// the server's description -- the CAD Viewer's server info, the CAD app's launch -- and
// the host installs it once, before a STEP model is drawn. This module only picks a
// rung from the camera; it holds no tolerance of its own.
let installed = null;

function finitePositive(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

/**
 * Install the ladder cadgen published: `{ levels: [{chordTolerance, angleTolerance}], defaultLevel }`.
 * Installing the same ladder again is a no-op; a different one replaces it.
 */
export function installTessellationLadder(published) {
  const levels = Array.isArray(published?.levels) ? published.levels : null;
  const defaultLevel = published?.defaultLevel;
  if (!levels?.length || !levels.every((level) => finitePositive(level?.chordTolerance) && finitePositive(level?.angleTolerance))
      || !Number.isInteger(defaultLevel) || defaultLevel < 0 || defaultLevel >= levels.length) {
    throw new Error(
      "cadgen's tessellation ladder is { levels: [{ chordTolerance, angleTolerance }, ...], defaultLevel }; "
      + `received ${JSON.stringify(published)}. Update cadgen and the app together.`
    );
  }
  const frozen = Object.freeze(levels.map(({ chordTolerance, angleTolerance }) => Object.freeze({ chordTolerance, angleTolerance })));
  installed = Object.freeze({
    levels: frozen,
    chordLevels: Object.freeze(frozen.map((level) => level.chordTolerance)),
    defaultLevel,
  });
  return installed;
}

function ladder() {
  if (!installed) {
    throw new Error(
      "The tessellation ladder is cadgen's: the host installs it (installTessellationLadder) from the "
      + "server's description before a STEP model is drawn."
    );
  }
  return installed;
}

/** The rung every model opens at. */
export function lodDefaultLevel() {
  return ladder().defaultLevel;
}

/** Every rung's tolerances, coarse to fine. */
export function lodTessellationLevels() {
  return ladder().levels;
}

/** Every rung's chord tolerance, coarse to fine: what the camera's projected error is measured in. */
export function lodChordLevels() {
  return ladder().chordLevels;
}

export function normalizeLodLevel(level) {
  const { levels, defaultLevel } = ladder();
  const numeric = Number(level);
  if (!Number.isFinite(numeric)) return defaultLevel;
  return Math.max(0, Math.min(levels.length - 1, Math.trunc(numeric)));
}

/** A rung's tolerances, both named: what a mesh request and its cache key say. */
export function lodTessellationForLevel(level) {
  return { ...ladder().levels[normalizeLodLevel(level)] };
}

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
export function desiredLevel(sample, levels = lodChordLevels(), targetPx = LOD_TARGET_PX) {
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
 * Moves at most one level per call. Pressure coarsening uses this step;
 * settledLevel folds repeated steps for an unchanged camera sample.
 */
export function nextLevel(sample, currentLevel, levels = lodChordLevels()) {
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
 * Final hysteresis level for one unchanged numeric sample. An upgrade's
 * previous error (>1.25) forbids reversing below .6; a downgrade lands below
 * .6 and cannot reverse above 1.25. There are at most N-1 moves. Keep nextLevel
 * as the authority so threshold arithmetic and starting-rung history agree.
 */
export function settledLevel(sample, currentLevel, levels = lodChordLevels()) {
  let level = Math.max(0, Math.min(levels.length - 1, currentLevel | 0));
  for (let check = 0; check < Math.max(1, levels.length); check += 1) {
    const next = nextLevel(sample, level, levels);
    if (next === level) return level;
    level = next;
  }
  throw new Error("LOD policy did not settle for an unchanged sample");
}

/**
 * Rank upgrade work, worst projected error first, so the nearest/largest
 * components on screen re-tessellate before distant specks. Entries:
 * { cid, currentLevel, sample } -> [{ cid, level, errorPx }] for entries whose
 * next level differs from the current one.
 */
export function planLodWork(entries, levels = lodChordLevels()) {
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
