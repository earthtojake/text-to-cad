import { useContext } from "react";
import { createPortal } from "react-dom";
import { ViewerElementContext } from "../../../host/context.js";
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
  const viewerElement = useContext(ViewerElementContext);
  const container = viewerElement?.current?.querySelector("[data-file-viewer-body]");
  const message = copyStatus || screenshotStatus;
  if (!message || previewMode) {
    return null;
  }

  const notification = (
    <ToastProvider duration={2200} swipeDirection="right">
      <Toast style={{ animation: "none" }}
        open={true}
        onOpenChange={(open) => {
          if (!open) {
            onClear?.();
          }
        }}
      >
        <ToastTitle>{message}</ToastTitle>
      </Toast>
      <ToastViewport className="absolute right-3 top-3 w-max max-w-[min(calc(100%-1.5rem),22rem)]" />
    </ToastProvider>
  );
  return container ? createPortal(notification, container) : notification;
}
