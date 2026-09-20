import { useEffect, useRef } from "react";
import { isEditableTarget } from "../viewport/dom.js";

const STATUS_TOAST_MS = 2200;

/**
 * Keyboard routing for one mounted viewer among several. Escape reaches
 * `onEscape` only when this viewer owns it: focus is inside it, or the key
 * landed on the page background after the last pointer press was inside it.
 * A composer, another pane and any editable target keep their own Escape.
 * Fullscreen's Escape is the host's. Transient copy/screenshot statuses clear
 * themselves after the toast's lifetime.
 *
 * @param {{ viewerElement: { current: HTMLElement | null } | null, escapeActive: boolean,
 *   onEscape: () => void, previewMode?: boolean, copyStatus?: string, screenshotStatus?: string,
 *   setCopyStatus?: (value: string) => void, setScreenshotStatus?: (value: string) => void }} options
 *   `escapeActive`: there is something for Escape to do (so idle viewers hold no listener).
 */
export function useViewerShortcuts({
  viewerElement, escapeActive, onEscape, previewMode = false,
  copyStatus = "", screenshotStatus = "", setCopyStatus, setScreenshotStatus
}) {
  const pointerInside = useRef(false);
  const escape = useRef(onEscape);
  escape.current = onEscape;
  useEffect(() => {
    const onPointerDown = event => { pointerInside.current = Boolean(viewerElement?.current?.contains(event.target)); };
    window.addEventListener("pointerdown", onPointerDown, true);
    return () => window.removeEventListener("pointerdown", onPointerDown, true);
  }, [viewerElement]);
  useEffect(() => {
    if (!(copyStatus || screenshotStatus)) return undefined;
    const timeoutId = window.setTimeout(() => {
      setCopyStatus?.("");
      setScreenshotStatus?.("");
    }, STATUS_TOAST_MS);
    return () => window.clearTimeout(timeoutId);
  }, [copyStatus, screenshotStatus, setCopyStatus, setScreenshotStatus]);
  useEffect(() => {
    if (!(escapeActive || previewMode)) return undefined;
    const handleKeyDown = (event) => {
      if (previewMode) return; // The host owns fullscreen Escape; tools are inactive.
      const element = viewerElement?.current;
      if (!element) return;
      const target = event.target;
      const inViewer = target instanceof Node && element.contains(target);
      const background = target === document.body || target === document || target === window;
      const focus = document.activeElement;
      if (!inViewer && !(background && pointerInside.current && (focus === document.body || (focus && element.contains(focus))))) return;
      if (event.key === "Escape" && !event.defaultPrevented && !isEditableTarget(event.target)) escape.current?.();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [viewerElement, escapeActive, previewMode]);
}
