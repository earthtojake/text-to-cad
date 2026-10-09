import { useEffect, useRef } from "react";
import { ringPoint } from "./feaResult.js";

const RING_RADIUS_PX = 14;
const COLOUR = { error: "#ef4444", warning: "#f59e0b" };

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
    let painted = "";
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
      const key = [width, height, dpr, tone, shownScale, runtime.camera.zoom, runtime.camera.matrixWorld.elements.join(),
        runtime.camera.projectionMatrix.elements.join(), shownMesh.matrixWorld.elements.join()].join("|");
      if (key === painted && paintedTargets === shownTargets) return;
      painted = key;
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
