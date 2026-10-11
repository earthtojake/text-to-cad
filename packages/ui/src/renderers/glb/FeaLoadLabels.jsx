import { useEffect, useRef } from "react";
import { GHOST_OPACITY } from "./feaMarkers.js";

// The panels' 11px, in the viewer's own face.
const FONT_SIZE = "500 11px";
// Past the arrows' free ends, away from the face, clear of the shafts.
const OFFSET_PX = 10;
// Whether the model hides a label is cast at most this often while the view moves, and once more
// when it stops: a ray through the result mesh per label, not per frame.
const HIDDEN_EVERY_MS = 100;

/**
 * Each load's amount ("300 N", "2 MPa") beside its arrows, drawn over the view on a canvas that
 * takes no pointer. `labels()` hands the current ones (`createFeaMarkers().labels`, in the result
 * mesh's space, following the deformation drawn); a frame loop repaints them, so they follow the
 * camera. A label behind the camera is left out. `colours`: the
 * ink and the halo it sits on. A label the model hides (a ray from the eye meets the part before
 * it) is drawn as its arrows are there, a faint ghost.
 */
export default function FeaLoadLabels({ runtimeRef, hostRef, mesh, labels, colours }) {
  const canvasRef = useRef(null);
  const live = useRef({ mesh, labels, colours });
  live.current = { mesh, labels, colours };
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    let frameId = 0;
    let painted = "";
    let castFor = "";
    let castAt = 0;
    let hidden = [];
    let raycaster = null;
    const paint = () => {
      frameId = window.requestAnimationFrame(paint);
      const runtime = runtimeRef.current;
      const host = hostRef.current;
      if (!runtime?.camera || !host) return;
      const { mesh: shownMesh, labels: read, colours: tones } = live.current;
      const width = host.clientWidth || 1;
      const height = host.clientHeight || 1;
      const dpr = window.devicePixelRatio || 1;
      runtime.camera.updateMatrixWorld();
      shownMesh.updateWorldMatrix(true, false);
      const point = new runtime.THREE.Vector3();
      const screen = (at) => {
        point.fromArray(at).applyMatrix4(shownMesh.matrixWorld);
        if (point.clone().applyMatrix4(runtime.camera.matrixWorldInverse).z >= -runtime.camera.near) return null;
        point.project(runtime.camera);
        return [((point.x + 1) * width) / 2, ((1 - point.y) * height) / 2];
      };
      const placed = [];
      for (const label of read()) {
        const free = screen(label.at);
        const face = label.face ? screen(label.face) : null;
        if (!free) continue;
        // On the far side of the free end from the face, the text running away from the arrow.
        const dx = face ? free[0] - face[0] : 1;
        const dy = face ? free[1] - face[1] : -1;
        const span = Math.hypot(dx, dy) || 1;
        placed.push({ text: label.text, at: label.at, x: free[0] + (dx / span) * OFFSET_PX, y: free[1] + (dy / span) * OFFSET_PX, align: dx < 0 ? "right" : "left" });
      }
      const where = JSON.stringify(placed.map(({ text, x, y }) => [text, Math.round(x), Math.round(y)]));
      const now = window.performance.now();
      if (where !== castFor && now - castAt >= HIDDEN_EVERY_MS) {
        castFor = where;
        castAt = now;
        raycaster ??= new runtime.THREE.Raycaster();
        const target = new runtime.THREE.Vector3();
        const ndc = new runtime.THREE.Vector2();
        hidden = placed.map(({ at }) => {
          target.fromArray(at).applyMatrix4(shownMesh.matrixWorld);
          const projected = target.clone().project(runtime.camera);
          raycaster.setFromCamera(ndc.set(projected.x, projected.y), runtime.camera);
          const reach = raycaster.ray.origin.distanceTo(target);
          raycaster.far = reach * 0.99;
          return raycaster.intersectObject(shownMesh, false).length > 0;
        });
      }
      placed.forEach((label, index) => { label.hidden = hidden[index] === true; });
      const key = JSON.stringify([width, height, dpr, tones, placed.map(({ text, x, y, align, hidden: ghost }) => [text, Math.round(x), Math.round(y), align, ghost])]);
      if (key === painted) return;
      painted = key;
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);
      context.font = `${FONT_SIZE} ${window.getComputedStyle(host).fontFamily || "sans-serif"}`;
      context.textBaseline = "middle";
      context.lineJoin = "round";
      for (const { text, x, y, align, hidden: ghost } of placed) {
        context.globalAlpha = ghost ? GHOST_OPACITY : 1;
        context.textAlign = align;
        context.lineWidth = 3;
        context.strokeStyle = tones.halo;
        context.strokeText(text, x, y);
        context.fillStyle = tones.ink;
        context.fillText(text, x, y);
      }
      context.globalAlpha = 1;
    };
    frameId = window.requestAnimationFrame(paint);
    return () => {
      window.cancelAnimationFrame(frameId);
      canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [runtimeRef, hostRef]);
  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden="true" data-fea-load-labels="" />;
}
