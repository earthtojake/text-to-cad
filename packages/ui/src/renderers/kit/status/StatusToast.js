import {
  Toast,
  ToastProvider,
  ToastTitle,
  ToastViewport
} from "@hardcore/ui/primitives/toast";

/**
 * The one line a viewer says about something it just did: a reference copied, a
 * snapshot delivered, a capture that could not be taken. Two slots, in the order
 * a person reads them — nothing here is an error, which is the alert dialog's.
 */
export default function StatusToast({ copyStatus, screenshotStatus, previewMode, onClear }) {
  const message = copyStatus || screenshotStatus;
  if (!message || previewMode) {
    return null;
  }

  return (
    <ToastProvider duration={2200} swipeDirection="right">
      <Toast
        open={true}
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
