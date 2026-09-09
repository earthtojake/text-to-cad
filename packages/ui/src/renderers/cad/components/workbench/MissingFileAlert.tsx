import { Alert, AlertDescription, AlertTitle } from "@hardcore/ui/primitives/alert";

export interface MissingFileAlertProps {
  missingFileRef: string;
  rootPath?: string;
  previewMode?: boolean;
}

export default function MissingFileAlert({ missingFileRef, rootPath = "", previewMode = false }: MissingFileAlertProps) {
  const missingFileLabel = String(missingFileRef || "").trim();
  // A Viewer resolves paths against ITS OWN served root. Point one at an
  // absolute path belonging to a different checkout — easy to do when an
  // instance from another clone is already holding the default port — and the
  // file is simply not found. Reporting that as "file does not exist" blames
  // the model and sends you looking for a build problem that isn't there, so
  // say which of the two it actually is.
  const servedRoot = String(
    rootPath || ""
  ).trim();
  const missingFileOutsideRoot = Boolean(
    missingFileLabel
    && servedRoot
    && missingFileLabel.startsWith("/")
    && !missingFileLabel.startsWith(servedRoot.endsWith("/") ? servedRoot : `${servedRoot}/`)
  );
  return (
    <>
      {!previewMode && missingFileLabel ? (
        <div className="pointer-events-none absolute inset-0 z-30 flex min-w-0 items-center justify-center px-4 py-4">
          <Alert
            variant="destructive"
            className="bg-popover pointer-events-auto w-full max-w-xl min-w-0 p-4 text-center shadow-lg"
          >
            <p className="col-start-1 text-tiny uppercase tracking-[0.16em] text-destructive">
              {missingFileOutsideRoot ? "Outside this viewer's root" : "File does not exist"}
            </p>
            <AlertTitle className="col-start-1 mt-1 line-clamp-none text-lg text-foreground">
              {missingFileOutsideRoot ? "Outside this viewer's root" : "File does not exist"}
            </AlertTitle>
            <AlertDescription className="col-start-1 mt-1 text-sm leading-6 text-muted-foreground">
              <code className="rounded-md bg-muted px-2 py-1 text-xs text-foreground">{missingFileLabel}</code>
              {missingFileOutsideRoot ? (
                <span className="mt-2 block text-xs leading-5">
                  This viewer serves{" "}
                  <code className="rounded bg-muted px-1 py-0.5 text-foreground">{servedRoot}</code>.
                  The path above is outside it — most likely a viewer from another
                  checkout is holding this port. Start one for this workspace on a
                  free port instead.
                </span>
              ) : null}
            </AlertDescription>
          </Alert>
        </div>
      ) : null}
    </>
  );
}
