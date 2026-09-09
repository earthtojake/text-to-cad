import {
  Toast,
  ToastProvider,
  ToastTitle,
  ToastViewport
} from "@hardcore/ui/primitives/toast";

export default function StatusToast({ copyStatus, screenshotStatus, persistenceStatus, motionErrorStatus, previewMode, onClear }) {
  const message = motionErrorStatus || copyStatus || screenshotStatus || persistenceStatus;
  const isError = Boolean(motionErrorStatus);
  if (!message || previewMode) {
    return null;
  }

  return (
    <ToastProvider duration={2200} swipeDirection="right">
      <Toast
        open={true}
        className={isError ? "border-destructive/40 text-destructive" : undefined}
        onOpenChange={(open) => {
          if (!open) {
            onClear?.();
          }
        }}
      >
        <ToastTitle>{message}</ToastTitle>
      </Toast>
      <ToastViewport />
    </ToastProvider>
  );
}
