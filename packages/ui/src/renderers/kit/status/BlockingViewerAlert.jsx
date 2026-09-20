import { CircleAlert } from "lucide-react";
import { cn } from "@hardcore/ui/utils";
import ViewerAlertBody from "./ViewerAlertBody.js";

/**
 * Which alert covers the viewport. An error always does; a warning only while
 * there is nothing on screen to look at instead, and never when it says
 * `blocking: false` (those ride the file's status badge and its dialog).
 */
export function blockingViewerAlert(alert, hasContent) {
  return alert && alert.blocking !== false && (alert.blocking || alert.severity !== "warning" || !hasContent) ? alert : null;
}

/** The card over the viewport for an alert that blocks it. */
export default function BlockingViewerAlert({ alert, onReload }) {
  if (!alert) return null;
  return (
    <div className="pointer-events-none absolute inset-0 z-30 flex min-w-0 items-center justify-center px-3 py-3 sm:px-4">
      <div
        role="alert"
        className="bg-popover pointer-events-auto w-full max-w-lg min-w-0 max-h-full overflow-y-auto rounded-lg border p-5 text-left shadow-md"
      >
        <h2 className="mb-3 flex items-start gap-2 text-base font-semibold leading-6 text-foreground">
          <CircleAlert className={cn("mt-0.5 size-5 shrink-0", alert.severity === "warning" ? "text-amber-500" : "text-destructive")} aria-hidden="true" />
          {alert.title || alert.summary || "Couldn’t display the model"}
        </h2>
        <ViewerAlertBody alert={alert} onReload={onReload} />
      </div>
    </div>
  );
}
