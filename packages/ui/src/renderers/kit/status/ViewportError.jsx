import { cn } from "@hardcore/ui/utils";
import { useViewerMobile } from "../../../file-viewer/responsive.js";

/**
 * A failure inside the running viewport — a lost WebGL context, a scene that could not be
 * applied — as one line under the tool strip. Load failures and alerts are the card's
 * (`ViewerAlertCard`); this is the viewport's own, and every viewport shows it this way.
 */
export default function ViewportError({ message }) {
  const mobile = useViewerMobile();
  if (!message) return null;
  return <p className={cn("bg-popover pointer-events-none absolute left-4 z-20 rounded-lg border border-error-border px-4 py-3 text-sm text-error shadow-sm",
    mobile ? "top-24" : "top-20")}>{message}</p>;
}
