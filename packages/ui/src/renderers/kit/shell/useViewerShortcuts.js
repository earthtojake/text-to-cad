import { useEffect, useRef } from "react";
import { isEditableTarget } from "../viewport/dom.js";

/**
 * Keyboard routing for one mounted viewer among several. Escape reaches
 * `onEscape` only when this viewer owns it: focus is inside it, or the key
 * landed on the page background after the last pointer press was inside it.
 * A composer, another pane and any editable target keep their own Escape.
 * Fullscreen's Escape is the host's.
 *
 * @param {{ viewerElement: { current: HTMLElement | null } | null, escapeActive: boolean,
 *   onEscape: () => void, onCopy?: () => boolean, previewMode?: boolean }} options
 *   `escapeActive`: there is something for Escape to do (so idle viewers hold no listener).
 */
export function useViewerShortcuts({
  viewerElement, escapeActive, onEscape, onCopy, previewMode = false
}) {
  const pointerInside = useRef(false);
  const copy = useRef(onCopy);
  copy.current = onCopy;
  const escape = useRef(onEscape);
  escape.current = onEscape;
  useEffect(() => {
    const onPointerDown = event => { pointerInside.current = Boolean(viewerElement?.current?.contains(event.target)); };
    window.addEventListener("pointerdown", onPointerDown, true);
    return () => window.removeEventListener("pointerdown", onPointerDown, true);
  }, [viewerElement]);
  useEffect(() => {
    if (!(escapeActive || previewMode || onCopy)) return undefined;
    const handleKeyDown = (event) => {
      if (previewMode) return; // The host owns fullscreen Escape; tools are inactive.
      const element = viewerElement?.current;
      if (!element) return;
      const target = event.target;
      const inViewer = target instanceof Node && element.contains(target);
      const background = target === document.body || target === document || target === window;
      const focus = document.activeElement;
      if (!inViewer && !(background && pointerInside.current && (focus === document.body || (focus && element.contains(focus))))) return;
      if (!event.defaultPrevented && !isEditableTarget(target) && !window.getSelection()?.toString() &&
          ((event.key.toLowerCase() === "c" && (event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey) || (event.key === "Insert" && event.ctrlKey))) {
        if (copy.current?.()) { event.preventDefault(); event.stopPropagation(); }
      }
      if (event.key === "Escape" && !event.defaultPrevented && !isEditableTarget(event.target)) escape.current?.();
    };
    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [viewerElement, escapeActive, previewMode, Boolean(onCopy)]);
}
