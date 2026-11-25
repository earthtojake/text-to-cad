import { useContext, useEffect, useRef, useState } from "react";
import { Check, CircleAlert, Copy, Download, X } from "lucide-react";
import { Button } from "../primitives/button.jsx";
import { Popover, PopoverAnchor, PopoverContent } from "../primitives/popover.jsx";
import { Spinner } from "../primitives/spinner.js";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { ViewerHostContext } from "../host/context.js";
import { useI18n } from "../i18n/index.js";
import type { UpdateFailure, UpdatePhase, UpdateState } from "./useUpdate.js";

/** The ring a 24px button's progress is drawn on: a 16px circle, as the icons are. */
const RADIUS = 6.5;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
/** The command that updates cad in a terminal, the failure's way on: the same on every computer. */
export const UPDATE_COMMAND = "cad update";
/** How long a copy's tick shows. */
const COPIED_MS = 1600;
/** The causes the page says in words of its own (`update.cause.<word>`); any other is said by the server's words. */
export const UPDATE_CAUSES = ["timeout", "no_program", "in_use", "denied", "disk_full", "network", "offline", "no_release",
  "python", "platform", "config_exclude", "config_index", "config_tls", "uv_old", "kept", "server_running", "helper_start",
  "helper_crash", "lost", "no_installer", "no_python", "packaged", "unknown"] as const;

/** A failure in the person's language: why it did not install, and what to do. */
export function failureWords(failure: UpdateFailure, t: (key: string, params?: Record<string, unknown>) => string): string {
  const installer = failure.installer === "pipx" ? "pipx" : failure.installer === "uv" ? "uv" : t("update.installer");
  if ((UPDATE_CAUSES as readonly string[]).includes(failure.cause)) return t(`update.cause.${failure.cause}`, { installer });
  return failure.said || t("update.cause.other");
}

/** The terminal's way on: `cad update`, and a copy of it through the host's clipboard (none: the text to select). */
function TerminalCommand() {
  const { t } = useI18n();
  const clipboard = useContext(ViewerHostContext)?.clipboard;
  const [copied, setCopied] = useState(false);
  const tick = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(tick.current), []);
  const canCopy = typeof clipboard?.writeText === "function";
  const copy = () => {
    clearTimeout(tick.current);
    // The write starts inside the press: a browser lets a page write its clipboard only then.
    let written: Promise<unknown>;
    try { written = Promise.resolve(clipboard!.writeText(UPDATE_COMMAND)); } catch (error) { written = Promise.reject(error); }
    written.then(() => {
      setCopied(true);
      tick.current = setTimeout(() => setCopied(false), COPIED_MS);
    }, () => setCopied(false));
  };
  return <div className="mt-2">
    <p>{t("update.terminal")}</p>
    <div className="relative mt-1 rounded-sm bg-muted" data-update-command="">
      <pre className="px-2 py-1.5 pr-8 font-mono text-xs text-foreground select-text">{UPDATE_COMMAND}</pre>
      {canCopy ? <TooltipHint content={copied ? t("update.copied") : t("update.copy")} side="bottom">
        <Button type="button" variant="ghost" size="icon-xs" aria-label={copied ? t("update.copied") : t("update.copy")}
          className="absolute right-1 top-1 size-icon-button text-muted-foreground hover:bg-background hover:text-foreground" onClick={copy}>
          {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        </Button>
      </TooltipHint> : null}
    </div>
  </div>;
}

/**
 * A newer text-to-cad, as the update button: a blue icon and nothing else, which a host hands the viewer
 * (`update`) to draw last among the navbar's controls, outermost, over every file and over the home, while
 * this install is behind (a newer release of its own major: `auto_update.button`'s `latest`). A click
 * updates (`useUpdate`): the icon becomes a ring that fills a stage at a time as the release installs (each
 * step eased), then a spinner while the server restarts, and the page reloads itself into the new release
 * (the host's to do). The tooltip says "Update", then the percent of the stages done, then that the server
 * restarts. An update that failed -- the button's own, a typed one, or cad's automatic one -- says why under
 * the button, in plain words, and what to do, with `cad update` to copy into a terminal; the button stays,
 * and a click tries again. The failure stays until the person puts it away (its X, or Escape) or another
 * attempt begins.
 */
export function UpdateButton({ state, phase, failure, onUpdate, onDismiss }: {
  state: UpdateState | null;
  phase: UpdatePhase;
  failure?: UpdateFailure | null;
  onUpdate(): void;
  onDismiss?(): void;
}) {
  const { t } = useI18n();
  const version = state?.latest ?? "";
  const blue = "bg-blue-500 text-white hover:bg-blue-600 dark:bg-blue-500 dark:hover:bg-blue-400";
  if (phase.phase === "restarting") {
    return <TooltipHint content={t("update.restarting", { version })}>
      <span className="inline-flex size-6 shrink-0 items-center justify-center" data-update="restarting">
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
        className="inline-flex size-6 shrink-0 items-center justify-center text-blue-500">
        <svg viewBox="0 0 16 16" className="size-4 -rotate-90" aria-hidden="true">
          <circle cx="8" cy="8" r={RADIUS} fill="none" stroke="currentColor" strokeOpacity={0.25} strokeWidth={2} />
          <circle cx="8" cy="8" r={RADIUS} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE} strokeDashoffset={CIRCUMFERENCE * (1 - share)}
            style={{ transition: "stroke-dashoffset 600ms ease-out" }} />
        </svg>
      </span>
    </TooltipHint>;
  }
  if (!version && !failure) return null;
  const button = <Button variant="default" size="icon-xs" aria-label={version ? t("update.toAria", { version }) : t("update.label")}
    data-update={failure ? "failed" : ""} className={`size-6 shrink-0 ${blue}`} onClick={onUpdate}>
    <Download className="size-3.5" aria-hidden="true" />
  </Button>;
  if (!failure) return <TooltipHint content={t("update.label")}>{button}</TooltipHint>;
  return <Popover open onOpenChange={(open: boolean) => { if (!open) onDismiss?.(); }}>
    <PopoverAnchor asChild><span className="inline-flex shrink-0"><TooltipHint content={t("update.label")}>{button}</TooltipHint></span></PopoverAnchor>
    {/* Not put away by a press elsewhere: the person works on, the failure stays until its X. */}
    <PopoverContent align="end" className="w-80 p-3 text-xs text-muted-foreground" role="alert" data-update-failure=""
      onInteractOutside={event => event.preventDefault()} onOpenAutoFocus={event => event.preventDefault()}>
      <div className="mb-1.5 flex items-start gap-2">
        <h2 className="flex min-w-0 flex-1 items-start gap-1.5 text-ui font-medium text-foreground">
          <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
          {version ? t("update.failedTo", { version }) : t("update.failed")}
        </h2>
        {onDismiss ? <Button type="button" variant="ghost" size="icon-xs" className="-mr-1 -mt-0.5" aria-label={t("update.dismiss")} onClick={onDismiss}>
          <X aria-hidden="true" />
        </Button> : null}
      </div>
      <p className="break-words text-foreground" data-update-cause={failure.cause}>{failureWords(failure, t)}</p>
      <TerminalCommand />
      {version ? <div className="mt-2.5 flex gap-2">
        <Button type="button" variant="outline" size="xs" onClick={onUpdate}>{t("update.retry")}</Button>
      </div> : null}
    </PopoverContent>
  </Popover>;
}
