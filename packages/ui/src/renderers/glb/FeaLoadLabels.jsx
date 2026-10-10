import { useEffect, useRef } from "react";

// The panels' 11px, in the viewer's own face.
const FONT_SIZE = "500 11px";
// Past the arrows' tails, away from their tips, clear of the shafts.
const OFFSET_PX = 10;

/**
 * Each load's amount ("300 N", "2 MPa") beside its arrows, drawn over the view on a canvas that
 * takes no pointer. `labels()` hands the current ones (`createFeaMarkers().labels`, in the result
 * mesh's space, following the deformation drawn); a frame loop repaints them, as the finding rings
 * are painted, so they follow the camera. A label behind the camera is left out. `colours`: the
 * ink and the halo it sits on.
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
        const tail = screen(label.at);
        const tip = label.tip ? screen(label.tip) : null;
        if (!tail) continue;
        // On the far side of the tail from the tip, the text running away from the arrow.
        const dx = tip ? tail[0] - tip[0] : 1;
        const dy = tip ? tail[1] - tip[1] : -1;
        const span = Math.hypot(dx, dy) || 1;
        placed.push({ text: label.text, x: tail[0] + (dx / span) * OFFSET_PX, y: tail[1] + (dy / span) * OFFSET_PX, align: dx < 0 ? "right" : "left" });
      }
      const key = JSON.stringify([width, height, dpr, tones, placed.map(({ text, x, y, align }) => [text, Math.round(x), Math.round(y), align])]);
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
      for (const { text, x, y, align } of placed) {
        context.textAlign = align;
        context.lineWidth = 3;
        context.strokeStyle = tones.halo;
        context.strokeText(text, x, y);
        context.fillStyle = tones.ink;
        context.fillText(text, x, y);
      }
    };
    frameId = window.requestAnimationFrame(paint);
    return () => {
      window.cancelAnimationFrame(frameId);
      canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [runtimeRef, hostRef]);
  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden="true" data-fea-load-labels="" />;
}
