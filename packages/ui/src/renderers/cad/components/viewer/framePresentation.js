// A newly allocated WebGL canvas has no presentable scene. Keep it covered
// until the destination mode has drawn content with its own lighting. Later
// presentation keys reuse that canvas: they acknowledge the newly reconciled
// scene after a real draw without hiding an already usable view.
export function createFramePresentation({ canvas, renderMode, onPresent }) {
  canvas.style.visibility = "hidden";
  let canvasPresented = false;
  let presentedKey = "";
  return {
    draw(runtime, drawFrame, request = null) {
      const key = String(request?.key || "");
      const ready = request?.ready === true;
      const hasVisibleContent = Boolean(runtime?.hasVisibleModel || runtime?.hasDrawingDocument);
      const environmentReady = !renderMode || runtime?.environmentReady === true;
      if (!canvasPresented && (!ready || !key || !hasVisibleContent || !environmentReady)) return false;
      drawFrame();
      if (!canvasPresented) {
        canvasPresented = true;
        canvas.style.visibility = "visible";
      }
      if (ready && key && key !== presentedKey && hasVisibleContent && environmentReady) {
        presentedKey = key;
        onPresent?.(key);
      }
      return true;
    }
  };
}

export function viewerTransitionBackdrop({ renderMode, renderConfiguration, background, viewerTheme }) {
  const color = (renderMode ? renderConfiguration?.backdrop?.color : background?.solidColor)
    || viewerTheme?.sceneBackground || "#f1f5f9";
  const hex = String(color).replace(/^#/, "");
  const rgb = (hex.length === 3 ? [...hex].map(value => value + value).join("") : hex);
  const luminance = /^[\da-f]{6}$/i.test(rgb)
    ? [0.2126, 0.7152, 0.0722].reduce((sum, weight, index) => (
        sum + weight * parseInt(rgb.slice(index * 2, index * 2 + 2), 16) / 255
      ), 0)
    : 1;
  return { backgroundColor: color, color: luminance > 0.5 ? "#334155" : "#e2e8f0" };
}
