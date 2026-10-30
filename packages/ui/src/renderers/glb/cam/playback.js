/**
 * A CAM result's routines on Preview's playbar (the renderer's own clips, `useGlbAnimation`): **Simulate**
 * plays the whole program, and a job with more than one setup adds **Simulate <setup>** for each. The
 * program's real time is played faster, the whole job in at most `SIMULATE_SECONDS` (one that is shorter
 * plays in real time), every clip at the same pace. A clip's moment is the program's time (`_CAM_T`).
 *
 * And what the scene's meshes are: the finished part, and the stock box it is cut from. Pure but for the
 * visibility it sets.
 */

import { english } from "../../../i18n/core.js";

export const SIMULATE_SECONDS = 30;
const MIN_SECONDS = 2;

/** How fast the program plays (clip seconds per program second), and its span. */
export function camTimeline(job) {
  const end = Math.max(job?.durationS || 0, ...(job?.operations || []).map((op) => op.t1), 0);
  const seconds = Math.min(Math.max(end, MIN_SECONDS), SIMULATE_SECONDS);
  return { from: 0, to: end, pace: end > 0 ? seconds / end : 1 };
}

/** Seconds one step lasts when motion is reduced: one operation a second. */
export const STEP_SECONDS = 1;

/**
 * The clips: `{ id, label, duration, play: { apply(elapsedSec), release() } }`, each moving `onMoment` to
 * `{ t, setup }` (the program's time, and the setup a setup's clip plays, null for Simulate) as it plays,
 * and to null when it lets go. None for a job with no time to play.
 *
 * With `reducedMotion` (the person's `prefers-reduced-motion`, or the app's own setting) nothing sweeps: a clip
 * steps one operation a second (`STEP_SECONDS`), each operation drawn whole at once with the tool at its end.
 */
export function camClips(job, onMoment, { reducedMotion = false, t = english } = {}) {
  const timeline = camTimeline(job);
  if (!(timeline.to > 0)) return [];
  const clip = (id, label, from, to, setup) => {
    if (reducedMotion) {
      const ends = job.operations.filter((op) => op.t1 > op.t0 && op.t0 >= from - 1e-9 && op.t1 <= to + 1e-9 && (!setup || op.setup === setup))
        .map((op) => op.t1).sort((a, b) => a - b);
      if (!ends.length) ends.push(to);
      const duration = ends.length * STEP_SECONDS;
      return {
        id, label, duration,
        play: {
          apply(elapsedSec) { onMoment({ t: ends[Math.min(Math.max(Math.floor(elapsedSec / STEP_SECONDS), 0), ends.length - 1)], setup }); },
          release() { onMoment(null); },
        },
      };
    }
    const duration = Math.max((to - from) * timeline.pace, MIN_SECONDS);
    return {
      id, label, duration,
      play: {
        apply(elapsedSec) { onMoment({ t: from + Math.min(Math.max(elapsedSec / duration, 0), 1) * (to - from), setup }); },
        release() { onMoment(null); },
      },
    };
  };
  const clips = [clip("cam:simulate", t("cam.simulate"), timeline.from, timeline.to, null)];
  if (job.setups.length > 1) {
    for (const setup of job.setups) {
      if (!setup.operations.length) continue;
      const from = Math.min(...setup.operations.map((op) => op.t0));
      const to = Math.max(...setup.operations.map((op) => op.t1));
      if (to > from) clips.push(clip(`cam:setup:${setup.id}`, t("cam.simulateSetup", { setup: setup.plain }), from, to, setup.id));
    }
  }
  return clips;
}

/** The result's meshes: the part's and the stock's (node extras `kind: "stock"`). */
export function camSceneMeshes(root) {
  const part = [];
  const stock = [];
  root?.traverse?.((object) => {
    if (!object.isMesh || object.userData?.camDrawn) return;
    (object.userData?.kind === "stock" ? stock : part).push(object);
  });
  return { part, stock };
}

/** Shows the part and the stock as Job's Show rows say. Returns whether anything changed. */
export function showCamMeshes(meshes, { part = true, stock = true } = {}) {
  let changed = false;
  const set = (objects, visible) => {
    for (const object of objects) if (object.visible !== visible) { object.visible = visible; changed = true; }
  };
  set(meshes.part, part);
  set(meshes.stock, stock);
  return changed;
}

/** A moment of the program as a clock: "0:45", "12:03", "1:02:05". */
export function formatClock(seconds) {
  const whole = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = String(whole % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/**
 * How fast a clip plays the program, in words: "12× speed" (the playbar's own `speed` times the pace the
 * program is fitted to), "Real time", or, with motion reduced, "One operation a second".
 */
export function playbackSpeedWords(job, { speed = 1, reducedMotion = false, t = english } = {}) {
  if (reducedMotion) return t("cam.stepPerSecond");
  const factor = (Number(speed) || 1) / camTimeline(job).pace;
  if (Math.abs(factor - 1) < 0.05) return t("cam.realTime");
  const shown = factor >= 10 ? Math.round(factor) : Math.round(factor * 10) / 10;
  return t("cam.speed", { factor: shown.toLocaleString("en-US") });
}

/**
 * What the readout over the playbar says at a moment: the operation under way (`op`, its index, where the tool's
 * place names it; else the last begun before then, in the setup the clip plays), the program's time over its whole
 * ("1:32 / 3:38"), and how fast it plays.
 */
export function camReadoutWords(job, moment, { op = null, speed = 1, reducedMotion = false, t = english } = {}) {
  if (!job || !moment) return null;
  const ops = job.operations.filter((entry) => !moment.setup || entry.setup === moment.setup);
  let current = op === null ? null : ops.find((entry) => entry.index === op) || null;
  if (!current) {
    // The last begun before the moment: at an operation's last moment, that operation, not the next.
    const sorted = [...ops].sort((a, b) => a.t0 - b.t0);
    current = sorted[0] || null;
    for (const entry of sorted) if (entry.t0 < moment.t - 1e-9) current = entry;
  }
  return {
    operation: current ? current.name || current.plain : "",
    time: `${formatClock(moment.t)} / ${formatClock(camTimeline(job).to)}`,
    speed: playbackSpeedWords(job, { speed, reducedMotion, t }),
  };
}
