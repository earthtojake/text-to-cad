import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from "../ui/alert-dialog";

// A title and a description. The severity colours the title; nothing else is
// rendered — no badge, no resolution paragraph, no command block.
export default function ViewerAlertDialog({
  viewerAlertOpen,
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
          <AlertDialogDescription className="leading-6 whitespace-pre-line break-words">
            {viewerAlert.message}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel aria-label="Close alert dialog">Close</AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
