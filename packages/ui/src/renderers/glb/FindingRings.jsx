import { useEffect, useRef } from "react";
import { ringPoint } from "./feaResult.js";

const RING_RADIUS_PX = 14;
const COLOUR = { error: "#ef4444", warning: "#f59e0b" };

/** Whether `seen` already holds every number of `lists`, in order; it takes them as it finds one that differs, with no array made for the matrices. */
function unchanged(seen, ...lists) {
  let same = true;
  let at = 0;
  for (const list of lists) {
    for (let index = 0; index < list.length; index += 1, at += 1) {
      if (seen[at] !== list[index]) { seen[at] = list[index]; same = false; }
    }
  }
  return same;
}

/**
 * A ring in screen space round each place the chosen finding names (`targets`: `ringTargets`, in
 * the result mesh's space), drawn over the view on a canvas that takes no pointer. A frame loop
 * repaints when the camera, the size, the deformation scale or the targets changed, so a ring
 * follows its point as the part is orbited and as the displacement is exaggerated. A point behind
 * the camera is left out.
 */
export default function FindingRings({ runtimeRef, hostRef, mesh, targets, severity, scale }) {
  const canvasRef = useRef(null);
  const live = useRef({ mesh, targets, severity, scale });
  live.current = { mesh, targets, severity, scale };
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    let frameId = 0;
    const painted = [];
    let paintedTone = null;
    let paintedTargets = null;
    const paint = () => {
      frameId = window.requestAnimationFrame(paint);
      const runtime = runtimeRef.current;
      const host = hostRef.current;
      if (!runtime?.camera || !host) return;
      const { mesh: shownMesh, targets: shownTargets, severity: tone, scale: shownScale } = live.current;
      const width = host.clientWidth || 1;
      const height = host.clientHeight || 1;
      const dpr = window.devicePixelRatio || 1;
      runtime.camera.updateMatrixWorld();
      shownMesh.updateWorldMatrix(true, false);
      const same = unchanged(painted, [width, height, dpr, shownScale, runtime.camera.zoom], runtime.camera.matrixWorld.elements,
        runtime.camera.projectionMatrix.elements, shownMesh.matrixWorld.elements);
      if (same && tone === paintedTone && paintedTargets === shownTargets) return;
      paintedTone = tone;
      paintedTargets = shownTargets;
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      const context = canvas.getContext("2d");
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);
      const point = new runtime.THREE.Vector3();
      for (const target of shownTargets) {
        point.fromArray(ringPoint(target, shownScale)).applyMatrix4(shownMesh.matrixWorld);
        if (point.clone().applyMatrix4(runtime.camera.matrixWorldInverse).z >= -runtime.camera.near) continue;
        point.project(runtime.camera);
        const x = ((point.x + 1) * width) / 2;
        const y = ((1 - point.y) * height) / 2;
        context.beginPath();
        context.arc(x, y, RING_RADIUS_PX, 0, Math.PI * 2);
        context.lineWidth = 5;
        context.strokeStyle = "rgba(0, 0, 0, 0.35)";
        context.stroke();
        context.lineWidth = 2.5;
        context.strokeStyle = COLOUR[tone] || COLOUR.warning;
        context.stroke();
      }
    };
    frameId = window.requestAnimationFrame(paint);
    return () => {
      window.cancelAnimationFrame(frameId);
      canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [runtimeRef, hostRef]);
  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden="true" data-fea-finding-rings="" />;
}
