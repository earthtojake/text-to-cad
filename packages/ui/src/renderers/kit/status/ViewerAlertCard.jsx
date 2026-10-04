import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { CircleAlert, X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { cn } from "@text-to-cad/ui/utils";
import { useFollow } from "../../../file-viewer/navigation/NavbarLinks.jsx";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { ViewerHostContext } from "../../../host/context.js";
import { alertIssueUrl } from "./reportIssue.js";

/**
 * Whether the card can be put away. The viewport is the one place a file's problem is said, so
 * it shows every alert; one the model survives can be dismissed: a failed update
 * (`blocking: false` — the previous version is still on screen) and a warning beside the model.
 */
export function alertDismissible(alert, hasContent) {
  return alert.blocking === false || (hasContent && alert.severity === "warning");
}

// The same failure raised again is the same alert, even as a new object.
const alertKey = alert => JSON.stringify([alert.severity, alert.title, alert.message, alert.reason, alert.details]);
/** What the card is headed, and what its icon in the navbar is called. */
const alertTitle = alert => alert.title || alert.summary || "Couldn’t display the model";
/** The card's icon colour: amber for a warning, the destructive red for an error. */
const alertTone = alert => alert.severity === "warning" ? "text-amber-500" : "text-destructive";

// The card's own icon, in its colour, as the navbar draws a renderer's action (`FileViewer.tsx`
// hands an action's `icon` its size).
const NavbarErrorIcon = ({ className, ...props }) => <CircleAlert {...props} className={cn(className, "text-destructive")} />;
const NavbarWarningIcon = ({ className, ...props }) => <CircleAlert {...props} className={cn(className, "text-amber-500")} />;
const NO_ACTIONS = Object.freeze([]);

/**
 * The card's dismissal, held by the frame that shows it (`RendererShell.jsx`, or a renderer that draws the card itself) so
 * that it outlives the card: which alert the person put away — only one the model survives
 * (`alertDismissible`) — for as long as that alert stands. Once it changes, or clears (a retry
 * that fails the same way is raised again), or another file opens (`scope`), the dismissal is
 * forgotten and the card shows. While an alert is put away, the navbar has the way back to it:
 * the card's own icon, in its colour, named after the alert, leftmost of the navbar's right-hand
 * controls — the renderer's navbar action (`onNavigationActionsChange`), before the host's update,
 * Settings and the view's controls. Pressing it brings the card back and takes the icon away. Where
 * there is no navbar (preview, a view shown small) there is no icon either.
 *
 * @param {object | null} alert  The alert the card shows.
 * @param {{ hasContent?: boolean, scope?: string,
 *   onNavigationActionsChange?: ((actions: readonly import("../../../file-viewer/types.js").FileNavigationAction[]) => void) | null }} [options]
 * @returns {{ dismissed: boolean, dismiss(): void }}
 */
export function useAlertDismissal(alert, { hasContent = false, scope = "", onNavigationActionsChange = null } = {}) {
  const key = alert ? alertKey(alert) : "";
  const [put, setPut] = useState(null);
  // The dismissal of the alert on screen alone: when it is not that alert any more, it is gone.
  const stale = put !== null && (put.key !== key || put.scope !== scope);
  if (stale) setPut(null);
  const dismissed = !stale && put !== null && Boolean(alert) && alertDismissible(alert, hasContent);
  const dismiss = useCallback(() => { if (key) setPut({ key, scope }); }, [key, scope]);
  const reopen = useCallback(() => setPut(null), []);
  const title = alert ? alertTitle(alert) : "";
  const warning = alert?.severity === "warning";
  const published = useRef(false);
  useEffect(() => {
    if (!onNavigationActionsChange) return;
    if (dismissed) {
      onNavigationActionsChange([{ id: "viewer-alert", label: title, icon: warning ? NavbarWarningIcon : NavbarErrorIcon, onInvoke: reopen }]);
      published.current = true;
    } else if (published.current) {
      onNavigationActionsChange(NO_ACTIONS);
      published.current = false;
    }
  }, [dismissed, title, warning, reopen, onNavigationActionsChange]);
  // Gone with the view: nothing of it is left in the navbar.
  useEffect(() => () => { if (published.current) onNavigationActionsChange?.(NO_ACTIONS); }, [onNavigationActionsChange]);
  return { dismissed, dismiss };
}

/**
 * The card over the viewport for the alert it shows. One the model survives can be put
 * away (`onDismiss`, while it stands: `useAlertDismissal`) — the previous version is there to
 * inspect and to pick from — and is brought back from its icon in the navbar. Long compiler
 * output stays complete in a scrollable diagnostic, never clipped. Retry reloads the file; where
 * the host has a tracker (`links.issues`), Report Issue beside it opens a new issue saying what the
 * card says, about `file` (its path as the alert names it, absolute: the issue names only the file,
 * and carries no path of this machine).
 */
export default function ViewerAlertCard({ alert: shown, hasContent, onReload, file = "", dismissed = false, onDismiss = null }) {
  const mobile = useViewerMobile();
  const host = useContext(ViewerHostContext);
  const follow = useFollow(host?.links);
  if (!shown || dismissed) return null;
  const dismissible = Boolean(onDismiss) && alertDismissible(shown, hasContent);
  const reason = String(shown.reason || "");
  const shortReason = reason.split("\n").find((line) => line.trim()) || "";
  const readableReason = shortReason.length > 360 ? `${shortReason.slice(0, 360)}…` : shortReason;
  const title = alertTitle(shown);
  const report = alertIssueUrl(host?.links?.issues, { ...shown, title },
    { file, version: host?.links?.version, platform: host?.environment.platform });
  return (
    <div className={cn("pointer-events-none absolute inset-0 z-30 flex min-w-0 items-center justify-center py-3", mobile ? "px-3" : "px-4")}>
      <div
        role="alert"
        className="bg-popover pointer-events-auto flex w-full max-w-lg min-w-0 max-h-full flex-col overflow-hidden rounded-lg border text-left shadow-md"
      >
        <ScrollArea className="min-h-0 flex-1" viewportClassName="p-5">
          <div className="mb-3 flex items-start gap-2">
            <h2 className="flex min-w-0 flex-1 items-start gap-2 text-base font-semibold leading-6 text-foreground">
              <CircleAlert className={cn("mt-0.5 size-5 shrink-0", alertTone(shown))} aria-hidden="true" />
              {title}
            </h2>
            {dismissible ? (
              <Button type="button" variant="ghost" size="icon-xs" aria-label="Dismiss"  onClick={onDismiss}>
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
                <ScrollArea className="mt-2 max-h-48 rounded-md bg-muted">
                  <pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs leading-5 select-text">{shown.details}</pre>
                </ScrollArea>
              </details>
            ) : null}
            {shown.reload || report ? (
              <div className="flex flex-wrap gap-2">
                {shown.reload ? (
                  <Button type="button" variant="outline" size="sm" onClick={onReload} disabled={!onReload}>
                    Retry
                  </Button>
                ) : null}
                {report ? (
                  <Button asChild variant="outline" size="sm">
                    <a href={report} target="_blank" rel="noreferrer" onClick={follow} data-report-issue="">Report Issue</a>
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
