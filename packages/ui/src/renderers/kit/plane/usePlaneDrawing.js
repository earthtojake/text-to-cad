/**
 * Draw on a flat picture: the shared drawing editor (`kit/tools/draw/DrawingOverlay.jsx`) laid over
 * the canvas, the person's sketch handed on as the view with its ink. While Draw is up the editor
 * owns pan and zoom and the picture follows it (`kit/tools/draw/planeViewLock.js`, through the one
 * lock every view's Draw uses, `useDrawingViewLock.js`), so ink and picture stay one picture.
 */
import { useCallback, useMemo } from "react";
import { useDrawingSession } from "../../../drawing/session.js";
import { CAD_DRAWING_DEFAULTS } from "../tools/draw/DrawingOverlay.jsx";
import { planeDrawingTarget } from "../tools/draw/planeViewLock.js";
import { useDrawingViewLock } from "../tools/draw/useDrawingViewLock.js";

/**
 * @param {{ active: boolean, noun?: string, plane: { transformRef: { current: object|null }, setView(transform: object): void,
 *   paintNow?: () => void, settle?: () => void, canvasRef: { current: HTMLCanvasElement|null } } }} options
 *   `plane.settle`: paint the picture final now (not a patch scaled while the view rests), before a capture.
 */
export function usePlaneDrawing({ active, plane, noun = "picture" }) {
  const drawing = useDrawingSession(active, CAD_DRAWING_DEFAULTS);
  const { transformRef, setView, paintNow, settle, canvasRef } = plane;
  const target = useMemo(() => planeDrawingTarget({ transformRef, setView, paintNow, canvasRef }), [transformRef, setView, paintNow, canvasRef]);
  const { drawingControllerRef, handleDrawingContent, handleDrawingReady, followDrawingViewport } = useDrawingViewLock({
    active, sketch: drawing.sketch ?? 0, drawing, target
  });

  /** The view as it is on screen, the picture with its overlay and the ink over it, as a PNG. */
  const capture = useCallback(() => new Promise((resolve, reject) => {
    const picture = canvasRef.current;
    if (!picture) { reject(new Error(`The ${noun} is not on screen yet.`)); return; }
    // A sketch made right after a zoom is copied as sharp as the picture will be once it rests.
    settle?.();
    const canvas = document.createElement("canvas");
    canvas.width = picture.width;
    canvas.height = picture.height;
    const context = canvas.getContext("2d");
    if (!context) { reject(new Error(`The browser cannot draw the ${noun}’s picture.`)); return; }
    context.drawImage(picture, 0, 0);
    const ink = drawingControllerRef.current?.inkCanvas?.();
    if (ink) context.drawImage(ink, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error(`The browser could not encode the ${noun} as a PNG.`))), "image/png");
  }), [canvasRef, settle, noun, drawingControllerRef]);

  return {
    drawing, capture,
    overlay: { drawing, onReady: handleDrawingReady, onContentChange: handleDrawingContent, onViewportChange: followDrawingViewport }
  };
}
