// The engine's one progress event, as every job it runs says where it is (cadgen's
// `engine/progress.py`): `{ kind, stage, job, outputs, detail, done, total, elapsedMs }`. `kind` is the
// job's (build, import, export, snapshot, inspect-measure) and `stage` one of that kind's, a closed
// vocabulary the engine checks; the page says each in the view's language by the key
// `progress.<kind>.<stage>` (`i18n/locales`), and never reads a word of the engine's own. This is the
// one reader of an event on the page: what it is, its key, its count.

// A kind is lower-case words with hyphens between; a stage is too, but one named for a technology keeps
// its name's digits (the update's `build123d`), as the engine's vocabulary policy allows.
const KIND = /^[a-z][a-z-]*$/;
const STAGE = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const KEY = /^progress\.([^.]+)\.([^.]+)$/;

/** Whether `frame` is the engine's progress event (a page's own loading frame says `phase`, never `kind`). */
export function isProgressEvent(frame) {
  return Boolean(frame) && typeof frame === "object" && typeof frame.kind === "string" && KIND.test(frame.kind)
    && typeof frame.stage === "string" && STAGE.test(frame.stage);
}

/** The locale key of an event's stage: `progress.build.body`. */
export function progressKey(frame) {
  return `progress.${frame.kind}.${frame.stage}`;
}

/** Whether a status label is an event's key (`statusLabel` says it through `t`). */
export function isProgressKey(label) {
  const key = KEY.exec(String(label || ""));
  return Boolean(key) && KIND.test(key[1]) && STAGE.test(key[2]);
}

/**
 * An event's count, where its stage has one: `done` of `total` as "120/628" and a percentage; a stage
 * whose units cannot be counted (`total` null or 0) says its stage alone, never a made-up fraction.
 */
export function progressFraction(frame) {
  const total = Number(frame?.total);
  const determinate = Number.isFinite(total) && total > 0;
  const done = determinate ? Math.max(0, Math.min(total, Number(frame.done) || 0)) : 0;
  return { determinate, counts: determinate ? `${done}/${total}` : "", percent: determinate ? Math.round((done / total) * 100) : null };
}
