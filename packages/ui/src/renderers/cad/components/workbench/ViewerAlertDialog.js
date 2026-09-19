import ViewerAlertBody from "./ViewerAlertBody.js";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from "@hardcore/ui/primitives/alert-dialog";

export default function ViewerAlertDialog({
  viewerAlertOpen,
  onReload,
  viewerAlert,
  previewMode,
  setViewerAlertOpen
}) {
  if (!viewerAlert || previewMode) {
    return null;
  }
  const isWarning = viewerAlert.severity === "warning";
  const compact = Boolean(viewerAlert.compact);

  return (
    <AlertDialog
      open={viewerAlertOpen}
      onOpenChange={setViewerAlertOpen}
    >
      <AlertDialogContent className={compact ? "max-w-sm" : "max-w-md"}>
        <AlertDialogHeader>
          <AlertDialogTitle className={isWarning ? "text-warning-foreground" : "text-destructive"}>
            {viewerAlert.title}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div><ViewerAlertBody alert={viewerAlert} onReload={onReload} /></div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel aria-label="Close alert dialog">Close</AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
