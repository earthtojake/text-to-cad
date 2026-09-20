import { useRef } from "react";

import { useJointHandles } from "./useJointHandles.js";

/**
 * The Pose tool's layer over the viewport: the canvas the handles are drawn on
 * and the label beside the hovered or held knob. Neither takes the pointer; the
 * knobs are hit-tested from the viewer's own element (`useJointHandles`).
 */
export default function JointHandleOverlay({ handles, runtimeRef, hostRef, layoutSeamRef, viewerReadyTick }) {
  const canvasRef = useRef(null);
  const labelRef = useRef(null);
  useJointHandles({ handles, runtimeRef, hostRef, canvasRef, labelRef, layoutSeamRef, viewerReadyTick });
  return (
    <>
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden="true" data-cad-joint-handles="" />
      <div
        ref={labelRef}
        hidden
        role="status"
        data-cad-joint-handle-label=""
        className="pointer-events-none absolute left-0 top-0 z-10 whitespace-pre rounded-md border border-border bg-background px-1.5 py-0.5 text-micro tabular-nums text-foreground shadow-sm"
      />
    </>
  );
}
