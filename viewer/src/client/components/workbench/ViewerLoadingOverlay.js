import { useEffect, useRef, useState } from "react";

import { Progress } from "@/components/ui/progress";
import {
  ARTIFACT_PROGRESS_POLL_MS,
  MAX_DISPLAY_PERCENT,
  continuedLoadingRatio,
  estimatedLoadingRatio,
  formatArtifactProgress
} from "@/workbench/artifactProgress.js";

// Two words, max. The status line names the stage; the number says how far along. Anything
// longer starts wrapping over the 3D scene and stops being scannable at a glance.
const DEFAULT_STATUS = "Loading";

/**
 * The one loading indicator: a status word top-left, a percent top-right, and a bar.
 *
 * The bar is ALWAYS shown while loading. When the build reports real progress we use it;
 * when it does not — a plain asset read, a decode, the window before a build's first
 * event — we estimate against the clock (see `estimatedLoadingRatio`). A bar that only
 * appears for the subset of loads that happen to be instrumented is worse than one that is
 * always there, because its absence reads as "stuck" rather than "unmeasured".
 *
 * A load can cross from measured to unmeasured HALFWAY THROUGH: an artifact build reports
 * real phases and then stops the moment it finishes, while the package GLB still has to be
 * fetched and decoded. The measured high-water mark is therefore kept as a floor and the
 * remainder eased from there (`continuedLoadingRatio`), so the bar neither jumps backwards
 * nor freezes at the from-scratch estimate's ceiling.
 */
export default function ViewerLoadingOverlay({
  viewerLoading,
  previewMode,
  progress = null
}) {
  const active = viewerLoading && !previewMode;
  const startedAtRef = useRef(0);
  // The highest ratio this load actually MEASURED, and when the measurement stopped. The
  // bar is monotonic within a load, so a floor is the whole mechanism: once something real
  // is known, no later estimate may walk it back.
  const measuredFloorRef = useRef(0);
  const tailStartedAtRef = useRef(0);
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!active) {
      startedAtRef.current = 0;
      measuredFloorRef.current = 0;
      tailStartedAtRef.current = 0;
      return undefined;
    }
    startedAtRef.current = Date.now();
    measuredFloorRef.current = 0;
    tailStartedAtRef.current = 0;
    // Repaint on the same cadence the artifact status is polled, so the estimated bar and
    // a reported one advance at one rate rather than two.
    const intervalId = window.setInterval(() => {
      setTick((current) => current + 1);
    }, ARTIFACT_PROGRESS_POLL_MS);
    return () => window.clearInterval(intervalId);
  }, [active]);

  if (!active) {
    return null;
  }

  const frame = progress ? formatArtifactProgress(progress) : null;
  let ratio;
  if (frame) {
    // Measured: record the high-water mark and clear any tail clock, so a build that
    // resumes reporting (a handoff to another run) goes back to real positions.
    measuredFloorRef.current = Math.max(measuredFloorRef.current, frame.ratio);
    tailStartedAtRef.current = 0;
    ratio = measuredFloorRef.current;
  } else if (measuredFloorRef.current > 0) {
    // The measured phase ended but the load did not — start the tail clock at the handover
    // (once; a re-render must not keep resetting it) and ease on from the floor.
    if (!tailStartedAtRef.current) {
      tailStartedAtRef.current = Date.now();
    }
    ratio = continuedLoadingRatio(measuredFloorRef.current, tailStartedAtRef.current);
  } else {
    ratio = estimatedLoadingRatio(startedAtRef.current);
  }
  // Derived from the ratio the bar is drawing, never from the raw frame: on a run handoff
  // the floor can sit above what the new run reports, and a number disagreeing with the bar
  // beside it is worse than either being slightly stale.
  const percent = Math.min(MAX_DISPLAY_PERCENT, Math.round(ratio * 100));
  const status = frame?.label || DEFAULT_STATUS;

  return (
    <div className="pointer-events-none absolute inset-0 z-20 overflow-hidden">
      <div className="cad-loading-overlay absolute inset-0" />
      <div className="absolute inset-0 flex items-center justify-center px-4">
        <div
          role="status"
          aria-live="polite"
          className="relative z-10 flex w-[22rem] max-w-[min(90vw,28rem)] flex-col gap-2 text-popover-foreground"
        >
          <div className="flex items-baseline justify-between gap-4">
            {/* smui: status text is uppercase with wide tracking. 11px is the skill's
                `text-label` size; this app has not registered that token, so it is
                written literally rather than adding a theme entry plus its
                tailwind-merge classGroup for one call site. */}
            <span className="truncate text-[11px] uppercase tracking-wider text-muted-foreground">
              {status}
            </span>
            <span className="text-[11px] tabular-nums text-muted-foreground">
              {percent}%
            </span>
          </div>
          <Progress value={percent} aria-label={status} />
        </div>
      </div>
    </div>
  );
}
