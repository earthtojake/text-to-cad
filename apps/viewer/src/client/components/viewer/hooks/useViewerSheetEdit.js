import { useEffect, useRef } from "react";

import { snapSheetPoint, viewAtSheetPoint } from "@/workbench/drawingEdits";

/**
 * Pointer editing on a drawing SHEET. The document arm lays the sheet in the
 * scene's x-y plane at z = 0 (sheet x -> x, sheet y -> y), so a pointer ray meets
 * it directly; there is no mesh to hit.
 *
 * "pick" is a smart dimension tool: the pointer snaps to the view's own line
 * work (corners, edges, holes) with a highlight, and a click reports the snap,
 * `onPick(snap)`. "move" highlights the view under the pointer and a drag
 * reports `onViewMove(name, dx, dy)` when it ends, with an outline following
 * the pointer meanwhile. The preview of the edit itself is the server's job.
 */
export function useViewerSheetEdit({
  runtimeRef,
  mountRef,
  enabled = false,
  tool = "",
  views = [],
  snapTargets = null,
  pickedPoints = [],
  onPick,
  onViewMove,
  viewerReadyTick = 0
}) {
  const callbacksRef = useRef({ onPick, onViewMove });
  callbacksRef.current = { onPick, onViewMove };
  const viewsRef = useRef(views);
  viewsRef.current = views;
  const targetsRef = useRef(snapTargets);
  targetsRef.current = snapTargets;

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
    const hoverGroup = new THREE.Group();
    overlay.add(hoverGroup);
    const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
    const hit = new THREE.Vector3();
    // The cursor goes on the canvas: the host's inline style is React's and gets rewritten.
    const cursorTarget = runtime.renderer?.domElement || container;

    const sheetPointFromEvent = (event) => {
      const rect = container.getBoundingClientRect();
      if (!rect.width || !rect.height) return null;
      runtime.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      runtime.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      runtime.raycaster.setFromCamera(runtime.pointer, runtime.camera);
      if (!runtime.raycaster.ray.intersectPlane(plane, hit)) return null;
      return [hit.x, hit.y];
    };
    // Sheet millimetres per screen pixel, so snap distances feel the same at any zoom.
    const mmPerPixel = () => {
      const rect = container.getBoundingClientRect();
      const camera = runtime.camera;
      if (!rect.height || !camera) return 0.5;
      if (camera.isOrthographicCamera) {
        return ((camera.top - camera.bottom) / (camera.zoom || 1)) / rect.height;
      }
      const distance = camera.position.distanceTo(runtime.controls?.target || new THREE.Vector3());
      return (2 * distance * Math.tan((camera.fov * Math.PI) / 360)) / rect.height;
    };

    const disposeChildren = (group) => {
      while (group.children.length) {
        const child = group.children.pop();
        child.geometry?.dispose?.();
        child.material?.dispose?.();
      }
    };
    const accent = new THREE.Color(0xe5484d);
    const flat = (color, opacity = 0.9) => new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true, opacity, side: THREE.DoubleSide });
    const outline = (view, dx = 0, dy = 0, strong = false) => {
      const x0 = view.minX + dx - 3;
      const x1 = view.maxX + dx + 3;
      const y0 = view.minY + dy - 3;
      const y1 = view.maxY + dy + 3;
      const points = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]].map(([x, y]) => new THREE.Vector3(x, y, 0.2));
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineDashedMaterial({ color: accent, dashSize: 3, gapSize: 2, depthTest: false, transparent: true, opacity: strong ? 1 : 0.45 })
      );
      line.computeLineDistances();
      line.renderOrder = 60;
      return line;
    };
    const ring = ([x, y], inner, outer) => {
      const mesh = new THREE.Mesh(new THREE.RingGeometry(inner, outer, 32), flat(accent));
      mesh.position.set(x, y, 0.2);
      mesh.renderOrder = 61;
      return mesh;
    };
    const bar = (a, b, width) => {
      const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(length, width), flat(accent, 0.7));
      mesh.position.set((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.2);
      mesh.rotation.z = Math.atan2(b[1] - a[1], b[0] - a[0]);
      mesh.renderOrder = 61;
      return mesh;
    };

    const idleGroup = new THREE.Group();
    overlay.add(idleGroup);
    const drawIdle = () => {
      disposeChildren(idleGroup);
      const scale = mmPerPixel();
      if (tool === "move") {
        for (const view of viewsRef.current) idleGroup.add(outline(view));
      } else if (tool === "pick") {
        for (const point of pickedPoints) idleGroup.add(ring(point, 3 * scale, 5 * scale));
      }
      runtime.requestRender?.();
    };
    drawIdle();

    let hoverKey = "";
    const drawHover = (snap, view) => {
      const key = snap ? `${snap.kind}:${snap.point[0].toFixed(2)},${snap.point[1].toFixed(2)}` : view ? `view:${view.name}` : "";
      if (key === hoverKey) return;
      hoverKey = key;
      disposeChildren(hoverGroup);
      const scale = mmPerPixel();
      if (snap?.kind === "vertex") {
        hoverGroup.add(ring(snap.point, 3 * scale, 5.5 * scale));
      } else if (snap?.kind === "dimension") {
        hoverGroup.add(ring(snap.point, 6 * scale, 8 * scale));
      } else if (snap?.kind === "edge") {
        hoverGroup.add(bar(snap.line.start, snap.line.end, 3 * scale));
      } else if (snap?.kind === "circle") {
        const r = snap.circle.radius;
        hoverGroup.add(ring(snap.circle.center, Math.max(r - 1.2 * scale, 0), r + 1.8 * scale));
      } else if (view) {
        hoverGroup.add(outline(view, 0, 0, true));
      }
      runtime.requestRender?.();
    };

    let drag = null;
    const onPointerMove = (event) => {
      const point = sheetPointFromEvent(event);
      if (drag) {
        if (!point) return;
        event.stopImmediatePropagation();
        const dx = point[0] - drag.start[0];
        const dy = point[1] - drag.start[1];
        drag.ghost.position.set(dx, dy, 0);
        runtime.requestRender?.();
        return;
      }
      if (!point) {
        drawHover(null, null);
        return;
      }
      if (tool === "pick") {
        const snap = snapSheetPoint(targetsRef.current, point, 10 * mmPerPixel());
        drawHover(snap, null);
        cursorTarget.style.cursor = snap ? "pointer" : "crosshair";
        // What the tool sees, for drivers and debugging: the snap kind and target count.
        container.dataset.sheetSnap = snap ? snap.kind : "none";
        container.dataset.sheetSnapTargets = String((targetsRef.current?.lines?.length || 0) + (targetsRef.current?.circles?.length || 0));
        container.dataset.sheetPoint = `${point[0].toFixed(1)},${point[1].toFixed(1)}`;
      } else if (tool === "move") {
        const view = viewAtSheetPoint(viewsRef.current, point);
        drawHover(null, view);
        cursorTarget.style.cursor = view ? "grab" : "default";
      }
    };
    const onPointerDown = (event) => {
      if (event.button !== 0) return;
      const point = sheetPointFromEvent(event);
      if (!point) return;
      if (tool === "pick") {
        const snap = snapSheetPoint(targetsRef.current, point, 10 * mmPerPixel());
        if (!snap) return;
        event.stopImmediatePropagation();
        event.preventDefault();
        callbacksRef.current.onPick?.(snap);
        return;
      }
      if (tool === "move") {
        const view = viewAtSheetPoint(viewsRef.current, point);
        if (!view) return;
        event.stopImmediatePropagation();
        event.preventDefault();
        drag = { view, start: point, ghost: outline(view, 0, 0, true) };
        overlay.add(drag.ghost);
        cursorTarget.style.cursor = "grabbing";
        container.setPointerCapture?.(event.pointerId);
      }
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
      cursorTarget.style.cursor = "grab";
      if (Math.abs(dx) >= 0.5 || Math.abs(dy) >= 0.5) {
        callbacksRef.current.onViewMove?.(view.name, dx, dy);
      }
      drawIdle();
    };
    const onPointerLeave = () => {
      if (!drag) drawHover(null, null);
    };

    container.addEventListener("pointerdown", onPointerDown, true);
    container.addEventListener("pointermove", onPointerMove, true);
    container.addEventListener("pointerup", onPointerUp, true);
    container.addEventListener("pointerleave", onPointerLeave, true);
    const previousCursor = cursorTarget.style.cursor;
    cursorTarget.style.cursor = tool === "pick" ? "crosshair" : "default";
    return () => {
      delete container.dataset.sheetSnap;
      delete container.dataset.sheetSnapTargets;
      delete container.dataset.sheetPoint;
      container.removeEventListener("pointerdown", onPointerDown, true);
      container.removeEventListener("pointermove", onPointerMove, true);
      container.removeEventListener("pointerup", onPointerUp, true);
      container.removeEventListener("pointerleave", onPointerLeave, true);
      cursorTarget.style.cursor = previousCursor;
      disposeChildren(hoverGroup);
      disposeChildren(idleGroup);
      runtime.scene.remove(overlay);
      runtime.requestRender?.();
    };
  }, [runtimeRef, mountRef, enabled, tool, pickedPoints, viewerReadyTick]);
}
