import { useLayoutEffect } from "react";

/**
 * How far a view's canvas (its stage) starts from the view's left edge — the docked panel's width,
 * open, else 0 — written onto the stage as `--cad-stage-left`, so the strip reaches back by that much
 * and stands at the view's centre whether the panel is open or not, over the panel where they meet
 * (Figma's toolbar stands over its layers panel the same way).
 *
 * It is written straight into the style, in the stage's resize observer, never through React state: an
 * observer runs after the layout that moved the stage and before that frame is painted, so the strip is
 * where it belongs in the very frame the panel opens, shuts or is dragged wider. Through state, the
 * render it asked for came a frame later, and the strip jumped by half the panel's width and back.
 *
 * @param {{ current: HTMLElement | null }} stageRef
 * @param {{ current: HTMLElement | null }} frameRef  The view's own box, the panel's and the stage's parent.
 */
export function useStageReach(stageRef, frameRef) {
  useLayoutEffect(() => {
    const stage = stageRef.current, frame = frameRef.current;
    if (!stage || !frame) return undefined;
    const place = () => stage.style.setProperty("--cad-stage-left", `${Math.round(stage.getBoundingClientRect().left - frame.getBoundingClientRect().left)}px`);
    place();
    if (typeof ResizeObserver === "undefined") return () => stage.style.removeProperty("--cad-stage-left");
    const observer = new ResizeObserver(place);
    observer.observe(stage);
    return () => { observer.disconnect(); stage.style.removeProperty("--cad-stage-left"); };
  }, [stageRef, frameRef]);
}

/** The strip's left inset (`inset` px from the view's left edge), reaching back over the docked panel. */
export const stripLeft = inset => `calc(${inset}px - var(--cad-stage-left, 0px))`;
