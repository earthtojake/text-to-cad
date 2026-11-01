import { Download } from "lucide-react";
import { Button } from "../primitives/button.jsx";
import { Spinner } from "../primitives/spinner.js";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { useI18n } from "../i18n/index.js";
import type { UpdateNotice, UpdatePhase } from "./useUpdate.js";

/** The ring a 24px button's progress is drawn on: a 16px circle, as the icons are. */
const RADIUS = 6.5;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * A newer text-to-cad, as the update button: an icon and nothing else, which a host hands the viewer
 * (`update`) to draw last among the navbar's controls, outermost, over every file and over the home (and, where
 * the host shows the view alone, in its corner), while this install is behind (`cad_server/updates.py`).
 * A click updates (`useUpdate`): the icon becomes a ring that fills a stage at a time as the release installs (each step eased), then a
 * spinner while the engine restarts, and the page reloads itself into the new release (the host's to
 * do). The tooltip says "Update", then the percent of the stages done, then that the engine restarts. Nothing else is shown; a failed update says its one line (the host's toast) and offers itself again.
 */
export function UpdateButton({ notice, phase, onUpdate }: {
  notice: UpdateNotice | null;
  phase: UpdatePhase;
  onUpdate(): void;
}) {
  const { t } = useI18n();
  const version = notice?.latest ?? "";
  const blue = "bg-blue-500 text-white hover:bg-blue-600 dark:bg-blue-500 dark:hover:bg-blue-400";
  if (phase.phase === "restarting") {
    return <TooltipHint content={t("update.restarting", { version })}>
      <span className="inline-flex size-6 items-center justify-center" data-update="restarting">
        <Spinner className="size-4" aria-label={t("update.restarting", { version })} />
      </span>
    </TooltipHint>;
  }
  if (phase.phase === "working") {
    const share = Math.min(1, (phase.done + 0.5) / Math.max(phase.total, 1));
    const percent = Math.round(100 * Math.min(1, phase.done / Math.max(phase.total, 1)));
    return <TooltipHint content={t("update.progress", { percent })}>
      <span role="progressbar" aria-label={t("update.updating", { version })} aria-valuemin={0}
      aria-valuemax={phase.total} aria-valuenow={phase.done} data-update="working"
      className="inline-flex size-6 items-center justify-center text-blue-500">
      <svg viewBox="0 0 16 16" className="size-4 -rotate-90" aria-hidden="true">
        <circle cx="8" cy="8" r={RADIUS} fill="none" stroke="currentColor" strokeOpacity={0.25} strokeWidth={2} />
        <circle cx="8" cy="8" r={RADIUS} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE} strokeDashoffset={CIRCUMFERENCE * (1 - share)}
          style={{ transition: "stroke-dashoffset 600ms ease-out" }} />
      </svg>
      </span>
    </TooltipHint>;
  }
  if (!notice) return null;
  return <TooltipHint content={t("update.label")}>
    <Button variant="default" size="icon-xs" aria-label={t("update.toAria", { version })} data-update=""
      className={`size-6 ${blue}`} onClick={onUpdate}>
      <Download className="size-3.5" aria-hidden="true" />
    </Button>
  </TooltipHint>;
}
