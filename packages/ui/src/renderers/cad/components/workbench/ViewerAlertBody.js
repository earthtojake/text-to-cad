import { Button } from "@hardcore/ui/primitives/button";
import { artifactWarningItems } from "../../workbench/artifactWarnings.js";

// Shared by the viewport and file-status dialog. Keep the explanation readable;
// long compiler output stays complete in a scrollable diagnostic, never clipped.
export default function ViewerAlertBody({ alert, onReload }) {
  const reason = String(alert.reason || "");
  const shortReason = reason.split("\n").find((line) => line.trim()) || "";
  const readableReason = shortReason.length > 360 ? `${shortReason.slice(0, 360)}…` : shortReason;
  // Backend advisories about the document's neighbours. Each one keeps the same
  // heading / explanation / recovery-step shape as the alert itself, so several
  // can be listed without any of them losing its next step. Every field here is
  // the server's own wording -- the client never composes warning text.
  const warnings = artifactWarningItems(alert);
  return (
    <div className="space-y-3 text-sm leading-6 text-muted-foreground">
      {alert.message ? <p className="whitespace-pre-line break-words">{alert.message}</p> : null}
      {warnings.length > 0 ? (
        <ul className="space-y-3" data-viewer-warnings={warnings.length}>
          {warnings.map((warning) => (
            <li
              key={`${warning.heading}|${warning.message}`}
              data-viewer-warning=""
              className="space-y-1"
            >
              {warning.heading ? (
                <p data-viewer-warning-heading="" className="break-words font-medium text-foreground">
                  {warning.heading}
                </p>
              ) : null}
              {warning.message ? (
                <p data-viewer-warning-message="" className="break-words">{warning.message}</p>
              ) : null}
              {warning.recovery ? (
                <p data-viewer-warning-recovery="" className="break-words">{warning.recovery}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {readableReason ? <p className="break-words text-foreground">{readableReason}</p> : null}
      {alert.recovery ? <p className="break-words">{alert.recovery}</p> : null}
      {alert.details ? (
        <details className="text-xs">
          <summary className="w-fit cursor-pointer rounded-sm text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring">Details</summary>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-mono text-xs leading-5 select-text">{alert.details}</pre>
        </details>
      ) : null}
      {alert.reload ? (
        <Button type="button" variant="outline" size="sm" onClick={onReload} disabled={!onReload}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}
