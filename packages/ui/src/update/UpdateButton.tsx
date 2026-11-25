import { useRef, useState } from "react";
import { Download } from "lucide-react";
import { Button } from "../primitives/button.jsx";
import { Popover, PopoverContent, PopoverTrigger } from "../primitives/popover.jsx";
import { Spinner } from "../primitives/spinner.js";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { useI18n } from "../i18n/index.js";
import { FLOATING_SURFACE_CLASS } from "../lib/floatingSurface.js";
import type { UpdatePhase, UpdateState } from "./useUpdate.js";

/** The ring a 24px button's progress is drawn on: a 16px circle, as the icons are. */
const RADIUS = 6.5;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * A newer text-to-cad, as the update button: a brand-blue icon and nothing else, which a host hands the viewer
 * (`update`) to draw last among the navbar's controls, outermost, over every file and over the home, while
 * this install is behind (a newer release of its own major: `auto_update.button`'s `latest`). A click
 * updates (`useUpdate`): the icon becomes a ring that fills a stage at a time as the release installs (each
 * step eased), then a spinner while the server restarts, and the page reloads itself into the new release
 * (the host's to do). The tooltip says "Update", then the percent of the stages done, then that the server
 * restarts. It is the same icon while a release is already installed beside this one, with only the server's
 * restart left (`ready`, whatever `latest` says). A click asks first, in a small popover under it that names the
 * release: "Update ready" and Restart, or "Update available" and Update, beside Later (which closes it and keeps
 * nothing); the primary updates, a ready release going straight to the spinner as nothing is left to install.
 * Nothing opens by itself. An update that failed -- the button's own, a typed one, or cad's automatic one -- is the viewer's alert
 * (`updateAlert`); the button stays as it is offered, and a click tries again.
 */
export function UpdateButton({ state, phase, onUpdate }: {
  state: UpdateState | null;
  phase: UpdatePhase;
  onUpdate(): void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const primary = useRef<HTMLButtonElement>(null);
  const ready = state?.state === "ready" ? state.ready ?? "" : "";
  const version = ready || (state?.latest ?? "");
  const brand = "bg-brand text-white hover:bg-brand-icon dark:text-primary-foreground dark:hover:bg-brand/75";
  if (phase.phase === "restarting") {
    const restarting = t("update.restarting", { version: phase.version || version });
    return <TooltipHint content={restarting}>
      <span className="inline-flex size-6 shrink-0 items-center justify-center" data-update="restarting">
        <Spinner className="size-4" aria-label={restarting} />
      </span>
    </TooltipHint>;
  }
  if (phase.phase === "working") {
    const share = Math.min(1, (phase.done + 0.5) / Math.max(phase.total, 1));
    const percent = Math.round(100 * Math.min(1, phase.done / Math.max(phase.total, 1)));
    return <TooltipHint content={t("update.progress", { percent })}>
      <span role="progressbar" aria-label={t("update.updating", { version })} aria-valuemin={0}
        aria-valuemax={phase.total} aria-valuenow={phase.done} data-update="working"
        className="inline-flex size-6 shrink-0 items-center justify-center text-brand-icon">
        <svg viewBox="0 0 16 16" className="size-4 -rotate-90" aria-hidden="true">
          <circle cx="8" cy="8" r={RADIUS} fill="none" stroke="currentColor" strokeOpacity={0.25} strokeWidth={2} />
          <circle cx="8" cy="8" r={RADIUS} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE} strokeDashoffset={CIRCUMFERENCE * (1 - share)}
            style={{ transition: "stroke-dashoffset 600ms ease-out" }} />
        </svg>
      </span>
    </TooltipHint>;
  }
  if (!version) return null;
  const words = ready
    ? { title: t("update.readyTitle"), text: t("update.readyText", { version }), action: t("update.restart") }
    : { title: t("update.availableTitle"), text: t("update.availableText", { version }), action: t("update.label") };
  // Not modal: Escape or a press outside closes it, and the focus goes back to the button.
  return <Popover open={open} onOpenChange={setOpen}>
    <TooltipHint content={t("update.label")}>
      <PopoverTrigger asChild>
        <Button variant="default" size="icon-xs" aria-label={t("update.toAria", { version })} data-update={ready ? "ready" : ""}
          className={`size-6 shrink-0 ${brand}`}>
          <Download className="size-3.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
    </TooltipHint>
    <PopoverContent align="end" sideOffset={8} collisionPadding={8} aria-label={words.title} data-update-prompt=""
      onOpenAutoFocus={event => { event.preventDefault(); primary.current?.focus(); }}
      className={`${FLOATING_SURFACE_CLASS} w-64 max-w-[calc(100vw-1rem)] p-3 text-xs`}>
      <p className="font-medium text-foreground">{words.title}</p>
      <p className="mt-1 text-muted-foreground">{words.text}</p>
      <div className="mt-3 flex justify-end gap-2">
        <Button variant="ghost" className="h-control px-2 text-xs font-normal" onClick={() => setOpen(false)}>{t("update.later")}</Button>
        <Button ref={primary} variant="default" className="h-control px-2 text-xs font-normal"
          onClick={() => { setOpen(false); onUpdate(); }}>{words.action}</Button>
      </div>
    </PopoverContent>
  </Popover>;
}
