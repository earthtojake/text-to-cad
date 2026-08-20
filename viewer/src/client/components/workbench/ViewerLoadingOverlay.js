import { Progress } from "@/components/ui/progress";
import { formatArtifactProgress } from "@/workbench/artifactProgress.js";

// Two words, max. Anything longer starts wrapping over the 3D scene and stops being
// scannable at a glance.
const DEFAULT_STATUS = "Loading";

/**
 * The one loading indicator: what is happening on the left, how far along on the right, bar.
 *
 * Two lines, never more. The status line is as SPECIFIC as the build can make it — the phase
 * plus the sub-unit in flight, on one line ("Building geometry · airframe") — because the
 * phase alone goes stale for minutes at a time on a big model, and a status that has not
 * changed in twenty minutes is the failure this whole pipeline exists to fix. Putting the
 * sub-unit on its own row instead cost a third row and made the overlay resize whenever a
 * phase started or stopped naming things; over a live 3D scene that was worse than the
 * information was worth.
 *
 * The phase ordinal ("2 of 4") is the one thing deliberately dropped: it answers a question
 * nobody asks mid-build, and it competed with the count for the eye.
 *
 * The bar takes one of two forms, chosen by what the build can honestly say. A phase that
 * knows its work list fills it and shows the count ("312/1127"); a phase that does not gets
 * an INDETERMINATE bar and NO number beside it. There is no overall percentage and no clock.
 * Both were previously required to keep one bar moving across four phases of unknowable
 * relative cost, and both lied: a first build had no measurements to weight the phases with,
 * so the bar sat at 0% for the whole of a ten-minute generate phase and then jumped to 46%.
 * A sliding bar says "working, no estimate" — which is the truth — and needs no repaint timer
 * to say it, because CSS animates it.
 */
export default function ViewerLoadingOverlay({
  viewerLoading,
  previewMode,
  progress = null
}) {
  if (!viewerLoading || previewMode) {
    return null;
  }

  const frame = progress ? formatArtifactProgress(progress) : null;
  const status = frame?.label || DEFAULT_STATUS;
  // Anything without a real fraction — an uncountable phase, or a plain asset read that
  // reports nothing at all — renders as indeterminate.
  const value = frame?.determinate ? frame.percent : null;

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
              {/* The sub-unit rides on the SAME line as the phase, in its authored case —
                  it is data ("airframe", "o1.7.3 nozzle_petal"), not a label, and shouting
                  it would make a content hash even harder to read. `truncate` on the parent
                  clips the pair from the right rather than letting it wrap over the scene. */}
              {frame?.detail ? (
                <span className="normal-case tracking-normal text-muted-foreground/60">
                  {" · "}
                  {frame.detail}
                </span>
              ) : null}
            </span>
            <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
              {frame?.counts || ""}
            </span>
          </div>
          <Progress value={value} aria-label={status} />
        </div>
      </div>
    </div>
  );
}
