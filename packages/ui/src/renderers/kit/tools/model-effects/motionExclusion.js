import { useEffect, useRef } from "react";

/**
 * One motion at a time: of a file's motions — Explode, its routine, Position and Clip, whichever it
 * has — the one SET off its default (its value changed: Explode's amount off zero, a routine owning
 * the pose, a joint moved, Clip on — never a tool merely taken up or a panel pressed) puts the others
 * back at theirs. Only a change on this file is setting one: a file that opens exploded and cut is
 * that file's view, and a file just opened sets nothing.
 *
 * @param {string} fileKey
 * @param {Record<string, { applied: boolean, reset: () => void }>} motions  Each motion's state now
 *   and how it goes back to its default.
 */
export function useMotionExclusion(fileKey, motions) {
  const latest = useRef(motions);
  latest.current = motions;
  const seen = useRef(null);
  const applied = Object.entries(motions).map(([id, motion]) => `${id}:${motion.applied ? 1 : 0}`).join(",");
  useEffect(() => {
    const now = Object.fromEntries(Object.entries(latest.current).map(([id, motion]) => [id, Boolean(motion.applied)]));
    const previous = seen.current;
    seen.current = { file: fileKey, applied: now };
    if (!previous || previous.file !== fileKey) return;
    const set = Object.keys(now).filter(id => now[id] && !previous.applied[id]);
    if (!set.length) return;
    for (const [id, motion] of Object.entries(latest.current)) {
      if (!set.includes(id) && motion.applied) motion.reset();
    }
  }, [fileKey, applied]);
}
