import { useContext, useId, useRef, useState, useSyncExternalStore } from "react";
import { CircleAlert, X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { cn } from "@text-to-cad/ui/utils";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { ViewerHostContext } from "../../../host/context.js";

/**
 * Which alert the viewport shows. An error always does, and the viewport is the one
 * place that says so: a failed update the model survives (`blocking: false` — the
 * previous version is still on screen) as much as one that leaves nothing to look at.
 * A warning shows only while there is nothing on screen instead; beside a model it is
 * the file's Issues' to list.
 */
export function viewportAlert(alert, hasContent) {
  return alert && (alert.severity !== "warning" || (!hasContent && alert.blocking !== false)) ? alert : null;
}

const NO_DESTINATION = { subscribe: () => () => {}, getSnapshot: () => null };

// The same failure raised again is the same alert, even as a new object.
const alertKey = alert => JSON.stringify([alert.severity, alert.title, alert.message, alert.reason, alert.details]);

/**
 * A retryable error is a load or build failure: the host may say what to do next in its own
 * environment and add actions beside Try again (`ViewerHost.loadFailures`). Without it the
 * card keeps the alert's own default text.
 */
export function hostRecovery(host, alert) {
  if (!host?.loadFailures || alert.severity !== "error" || !alert.reload) return null;
  const { kind, file, title, summary, message, reason, details } = alert;
  return host.loadFailures.recover({ kind, file, title: title || summary || "", message, reason, details, blocking: alert.blocking !== false }) || null;
}

/**
 * The card over the viewport for the alert it shows. One the model survives can be put
 * away — the previous version is there to inspect and to pick from — until the alert
 * changes, or clears and is raised again (a retry that failed the same way). Long
 * compiler output stays complete in a scrollable diagnostic, never clipped.
 */
/** A raw diagnostic folded behind a "Details" disclosure. The text inherits its size from `className`. */
export function DiagnosticDetails({ text, className }) {
  return (
    <details className={cn("text-xs", className)}>
      <summary className="w-fit cursor-pointer rounded-sm text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring">Details</summary>
      <ScrollArea className="mt-2 max-h-48 rounded-md bg-muted">
        <pre className="whitespace-pre-wrap break-words p-3 font-mono leading-5 select-text">{text}</pre>
      </ScrollArea>
    </details>
  );
}

export default function ViewerAlertCard({ alert, hasContent, onReload }) {
  const shown = viewportAlert(alert, hasContent);
  const mobile = useViewerMobile();
  const host = useContext(ViewerHostContext);
  const [dismissed, setDismissed] = useState("");
  const [outcome, setOutcome] = useState({ key: "", text: "" });
  const [pending, setPending] = useState(false);
  const running = useRef(false);
  const reasonId = useId();
  // A host's actions may depend on its prompt destination (a chat that went away): the card
  // re-asks the host whenever that destination changes, as PromptContextAction does.
  const destination = host?.promptContext || NO_DESTINATION;
  useSyncExternalStore(destination.subscribe, destination.getSnapshot, destination.getSnapshot);
  if (!shown) {
    if (dismissed) setDismissed("");
    return null;
  }
  const key = alertKey(shown);
  const dismissible = shown.blocking === false;
  if (dismissible && dismissed === key) return null;
  const recovered = hostRecovery(host, shown);
  const message = recovered?.message ?? shown.message;
  const recovery = recovered?.recovery ?? shown.recovery;
  const actions = recovered?.actions || [];
  // One action at a time: a second click cannot deliver the diagnostic twice.
  const run = (action) => {
    if (running.current || action.disabled) return;
    running.current = true;
    setPending(true);
    let result;
    try { result = action.run(); } catch (error) { result = Promise.reject(error); }
    void Promise.resolve(result).then(
      text => setOutcome({ key, text: typeof text === "string" ? text : "" }),
      error => setOutcome({ key, text: error instanceof Error ? error.message : String(error) }))
      .finally(() => { running.current = false; setPending(false); });
  };
  const reason = String(shown.reason || "");
  const shortReason = reason.split("\n").find((line) => line.trim()) || "";
  const readableReason = shortReason.length > 360 ? `${shortReason.slice(0, 360)}…` : shortReason;
  return (
    <div className={cn("pointer-events-none absolute inset-0 z-30 flex min-w-0 items-center justify-center py-3", mobile ? "px-3" : "px-4")}>
      <div
        role="alert"
        className="bg-popover pointer-events-auto flex w-full max-w-lg min-w-0 max-h-full flex-col overflow-hidden rounded-lg border text-left shadow-md"
      >
        <ScrollArea className="min-h-0 flex-1" viewportClassName="p-5">
          <div className="mb-3 flex items-start gap-2">
            <h2 className="flex min-w-0 flex-1 items-start gap-2 text-base font-semibold leading-6 text-foreground">
              <CircleAlert className={cn("mt-0.5 size-5 shrink-0", shown.severity === "warning" ? "text-amber-500" : "text-destructive")} aria-hidden="true" />
              {shown.title || shown.summary || "Couldn’t display the model"}
            </h2>
            {dismissible ? (
              <Button type="button" variant="ghost" size="icon-xs" aria-label="Dismiss"  onClick={() => setDismissed(key)}>
                <X aria-hidden="true" />
              </Button>
            ) : null}
          </div>
          <div className="space-y-3 text-sm leading-6 text-muted-foreground">
            {message ? <p className="whitespace-pre-line break-words">{message}</p> : null}
            {readableReason ? <p className="break-words text-foreground">{readableReason}</p> : null}
            {recovery ? <p className="break-words">{recovery}</p> : null}
            {shown.details ? <DiagnosticDetails text={shown.details} /> : null}
            {shown.reload || actions.length ? (
              <div className="flex flex-wrap items-center gap-2">
                {shown.reload ? (
                  <Button type="button" variant="outline" size="sm" onClick={onReload} disabled={!onReload}>
                    Try again
                  </Button>
                ) : null}
                {actions.map((action, index) => (
                  // An unavailable action stays focusable (`aria-disabled`, its click a no-op) so its
                  // reason, shown under the buttons, is its description for every reader.
                  <Button key={action.label} type="button" variant="outline" size="sm" onClick={() => run(action)}
                    disabled={pending && !action.disabled}
                    aria-disabled={action.disabled ? "true" : undefined}
                    aria-describedby={action.disabled && action.reason ? `${reasonId}-${index}` : undefined}
                    className="aria-disabled:cursor-not-allowed aria-disabled:opacity-50">
                    {action.label}
                  </Button>
                ))}
              </div>
            ) : null}
            {actions.map((action, index) => action.disabled && action.reason
              ? <p key={action.label} id={`${reasonId}-${index}`} className="break-words text-xs">{action.reason}</p> : null)}
            {outcome.key === key && outcome.text ? <p role="status" className="break-words text-xs">{outcome.text}</p> : null}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
