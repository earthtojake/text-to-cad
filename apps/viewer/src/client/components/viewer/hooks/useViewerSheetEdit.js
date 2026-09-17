import { useEffect, useRef } from "react";

/**
 * Pointer editing on a drawing SHEET: pick points for a new dimension, or drag a
 * view to a new place. The document arm lays the sheet in the scene's x-y plane
 * at z = 0 (sheet x -> x, sheet y -> y; the paper sits just behind it), so a
 * pointer ray meets it directly; there is no mesh to hit.
 *
 * The hook only reports: `onPick([x, y])` with sheet millimetres when the tool
 * is "pick", and `onViewMove(name, dx, dy)` when a drag under the "move" tool
 * ends. While a drag is in flight it shows a rectangle of the view's extent
 * following the pointer, and while picking it marks the points picked so far.
 * The preview of the edit itself is the server's job (the SVG re-renders).
 */
export function useViewerSheetEdit({
  runtimeRef,
  mountRef,
  enabled = false,
  tool = "",
  views = [],
  pickedPoints = [],
  onPick,
  onViewMove,
  viewerReadyTick = 0
}) {
  const callbacksRef = useRef({ onPick, onViewMove });
  callbacksRef.current = { onPick, onViewMove };
  const viewsRef = useRef(views);
  viewsRef.current = views;

  useEffect(() => {
    const runtime = runtimeRef?.current;
    const container = mountRef?.current;
    const THREE = runtime?.THREE;
    if (!enabled || !tool || !runtime || !container || !THREE) {
      return undefined;
    }
    const overlay = new THREE.Group();
    overlay.userData.sheetEditOverlay = true;
    runtime.scene.add(overlay);
    const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
    const hit = new THREE.Vector3();

    const sheetPointFromEvent = (event) => {
      const rect = container.getBoundingClientRect();
      if (!rect.width || !rect.height) return null;
      runtime.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      runtime.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      runtime.raycaster.setFromCamera(runtime.pointer, runtime.camera);
      if (!runtime.raycaster.ray.intersectPlane(plane, hit)) return null;
      return [hit.x, hit.y];
    };

    const clearOverlay = () => {
      while (overlay.children.length) {
        const child = overlay.children.pop();
        child.geometry?.dispose?.();
        child.material?.dispose?.();
      }
    };
    const accent = new THREE.Color(0xe5484d);
    const rectangle = (view, dx = 0, dy = 0) => {
      const x0 = view.minX + dx - 3;
      const x1 = view.maxX + dx + 3;
      const y0 = view.minY + dy - 3;
      const y1 = view.maxY + dy + 3;
      const points = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]].map(([x, y]) => new THREE.Vector3(x, y, 0.2));
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineDashedMaterial({ color: accent, dashSize: 3, gapSize: 2, depthTest: false, transparent: true, opacity: 0.9 })
      );
      line.computeLineDistances();
      line.renderOrder = 60;
      return line;
    };
    const marker = ([x, y]) => {
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(1.2, 2.0, 24),
        new THREE.MeshBasicMaterial({ color: accent, depthTest: false, transparent: true, opacity: 0.95, side: THREE.DoubleSide })
      );
      ring.position.set(x, y, 0.2);
      ring.renderOrder = 61;
      return ring;
    };

    const drawIdle = () => {
      clearOverlay();
      if (tool === "move") {
        for (const view of viewsRef.current) overlay.add(rectangle(view));
      } else if (tool === "pick") {
        for (const point of pickedPoints) overlay.add(marker(point));
      }
      runtime.requestRender?.();
    };
    drawIdle();

    let drag = null;
    const onPointerDown = (event) => {
      if (event.button !== 0) return;
      const point = sheetPointFromEvent(event);
      if (!point) return;
      if (tool === "pick") {
        event.stopImmediatePropagation();
        event.preventDefault();
        callbacksRef.current.onPick?.(point);
        return;
      }
      if (tool === "move") {
        const view = viewsRef.current.find((candidate) => (
          point[0] >= candidate.minX - 4 && point[0] <= candidate.maxX + 4
          && point[1] >= candidate.minY - 4 && point[1] <= candidate.maxY + 4
        ));
        if (!view) return;
        event.stopImmediatePropagation();
        event.preventDefault();
        drag = { view, start: point, ghost: rectangle(view) };
        overlay.add(drag.ghost);
        container.setPointerCapture?.(event.pointerId);
      }
    };
    const onPointerMove = (event) => {
      if (!drag) return;
      const point = sheetPointFromEvent(event);
      if (!point) return;
      event.stopImmediatePropagation();
      const dx = point[0] - drag.start[0];
      const dy = point[1] - drag.start[1];
      drag.ghost.position.set(dx, dy, 0);
      runtime.requestRender?.();
    };
    const onPointerUp = (event) => {
      if (!drag) return;
      event.stopImmediatePropagation();
      const point = sheetPointFromEvent(event) || drag.start;
      const dx = Math.round((point[0] - drag.start[0]) * 10) / 10;
      const dy = Math.round((point[1] - drag.start[1]) * 10) / 10;
      const { view } = drag;
      overlay.remove(drag.ghost);
      drag.ghost.geometry.dispose();
      drag.ghost.material.dispose();
      drag = null;
      container.releasePointerCapture?.(event.pointerId);
      if (Math.abs(dx) >= 0.5 || Math.abs(dy) >= 0.5) {
        callbacksRef.current.onViewMove?.(view.name, dx, dy);
      }
      drawIdle();
    };

    container.addEventListener("pointerdown", onPointerDown, true);
    container.addEventListener("pointermove", onPointerMove, true);
    container.addEventListener("pointerup", onPointerUp, true);
    const previousCursor = container.style.cursor;
    container.style.cursor = tool === "pick" ? "crosshair" : "grab";
    return () => {
      container.removeEventListener("pointerdown", onPointerDown, true);
      container.removeEventListener("pointermove", onPointerMove, true);
      container.removeEventListener("pointerup", onPointerUp, true);
      container.style.cursor = previousCursor;
      clearOverlay();
      runtime.scene.remove(overlay);
      runtime.requestRender?.();
    };
  }, [runtimeRef, mountRef, enabled, tool, pickedPoints, viewerReadyTick]);
}
