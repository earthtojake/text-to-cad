import { Button } from "@hardcore/ui/primitives/button";

// Shared by the viewport and file-status dialog. Keep the explanation readable;
// long compiler output stays complete in a scrollable diagnostic, never clipped.
export default function ViewerAlertBody({ alert, onReload }) {
  const reason = String(alert.reason || "");
  const shortReason = reason.split("\n").find((line) => line.trim()) || "";
  const readableReason = shortReason.length > 360 ? `${shortReason.slice(0, 360)}…` : shortReason;
  return (
    <div className="space-y-3 text-sm leading-6 text-muted-foreground">
      {alert.message ? <p className="whitespace-pre-line break-words">{alert.message}</p> : null}
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
