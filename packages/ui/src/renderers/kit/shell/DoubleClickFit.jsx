import { useEffect, useRef } from "react";
import { pickSceneAt } from "../tools/select/sceneMenu.js";
import { doubleClickFits } from "../viewport/dom.js";

/**
 * A double-click on empty space under Select fits the model, as F does and as every flat view's
 * double-click does: what the renderer, ink or a knob took first (`defaultPrevented`, or a capture
 * that stopped it) is theirs, and so is a double-click on something the scene picks. Every 3D view's:
 * a renderer's own frame (`RendererShell.jsx`) or a flat view's frame showing a 3D view. Under Select
 * only, by the one rule every view's double-click keeps (`viewport/dom.js`'s `doubleClickFits`).
 *
 * @param {{ viewport: { hostRef: object, runtimeRef: object, viewerReadyTick: number }, scene: object | null,
 *   viewerRef: { current: { resetZoom?: () => unknown } | null } }} props
 */
export default function DoubleClickFit({ viewport, scene, viewerRef }) {
  const { hostRef, runtimeRef, viewerReadyTick } = viewport;
  const live = useRef(null);
  live.current = { scene };
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    const onDoubleClick = (event) => {
      const now = live.current;
      const canvas = runtimeRef.current?.renderer?.domElement;
      if (event.defaultPrevented || event.target !== canvas || !doubleClickFits(canvas)) return;
      if (pickSceneAt({ hostRef, runtimeRef }, now.scene, event.clientX, event.clientY)) return;
      viewerRef.current?.resetZoom?.();
    };
    host.addEventListener("dblclick", onDoubleClick);
    return () => host.removeEventListener("dblclick", onDoubleClick);
  }, [hostRef, runtimeRef, viewerReadyTick, viewerRef]);
  return null;
}
