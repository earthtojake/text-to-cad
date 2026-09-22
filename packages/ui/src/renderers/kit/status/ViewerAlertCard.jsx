import { useState } from "react";
import { CircleAlert, X } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { cn } from "@hardcore/ui/utils";

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

// The same failure raised again is the same alert, even as a new object.
const alertKey = alert => JSON.stringify([alert.severity, alert.title, alert.message, alert.reason, alert.details]);

/**
 * The card over the viewport for the alert it shows. One the model survives can be put
 * away — the previous version is there to inspect and to pick from — until the alert
 * changes, or clears and is raised again (a retry that failed the same way). Long
 * compiler output stays complete in a scrollable diagnostic, never clipped.
 */
export default function ViewerAlertCard({ alert, hasContent, onReload }) {
  const shown = viewportAlert(alert, hasContent);
  const [dismissed, setDismissed] = useState("");
  if (!shown) {
    if (dismissed) setDismissed("");
    return null;
  }
  const key = alertKey(shown);
  const dismissible = shown.blocking === false;
  if (dismissible && dismissed === key) return null;
  const reason = String(shown.reason || "");
  const shortReason = reason.split("\n").find((line) => line.trim()) || "";
  const readableReason = shortReason.length > 360 ? `${shortReason.slice(0, 360)}…` : shortReason;
  return (
    <div className="pointer-events-none absolute inset-0 z-30 flex min-w-0 items-center justify-center px-3 py-3 sm:px-4">
      <div
        role="alert"
        className="bg-popover pointer-events-auto w-full max-w-lg min-w-0 max-h-full overflow-y-auto rounded-lg border p-5 text-left shadow-md"
      >
        <div className="mb-3 flex items-start gap-2">
          <h2 className="flex min-w-0 flex-1 items-start gap-2 text-base font-semibold leading-6 text-foreground">
            <CircleAlert className={cn("mt-0.5 size-5 shrink-0", shown.severity === "warning" ? "text-amber-500" : "text-destructive")} aria-hidden="true" />
            {shown.title || shown.summary || "Couldn’t display the model"}
          </h2>
          {dismissible ? (
            <Button type="button" variant="ghost" size="icon-xs" aria-label="Dismiss" title="Dismiss" onClick={() => setDismissed(key)}>
              <X aria-hidden="true" />
            </Button>
          ) : null}
        </div>
        <div className="space-y-3 text-sm leading-6 text-muted-foreground">
          {shown.message ? <p className="whitespace-pre-line break-words">{shown.message}</p> : null}
          {readableReason ? <p className="break-words text-foreground">{readableReason}</p> : null}
          {shown.recovery ? <p className="break-words">{shown.recovery}</p> : null}
          {shown.details ? (
            <details className="text-xs">
              <summary className="w-fit cursor-pointer rounded-sm text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring">Details</summary>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-mono text-xs leading-5 select-text">{shown.details}</pre>
            </details>
          ) : null}
          {shown.reload ? (
            <Button type="button" variant="outline" size="sm" onClick={onReload} disabled={!onReload}>
              Try again
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
