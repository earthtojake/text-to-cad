import { useEffect, useRef } from "react";

import {
  JOINT_HANDLE_ARM_PX,
  JOINT_HANDLE_HIT_PX,
  JOINT_HANDLE_TOUCH_HIT_PX,
  drawJointHandles,
  formatJointHandleValue,
  jointHandleAt
} from "./jointHandleCanvas.js";
import { add, advanceJointDrag, arcPoints, beginJointDrag, handleArmDirection, scale } from "./jointHandleMath.js";

// Above this many handles a model at rest shows knobs only: two dozen arms and
// travel arcs over one model read as a hedgehog, not as controls.
const QUIET_HANDLE_COUNT = 12;
const LABEL_OFFSET_PX = 14;

/**
 * Lay the handles out for the camera as it is now: every handle in WORLD space
 * (the list is in model space, under the model group) and its screen points.
 * A handle whose pivot or knob is behind the camera is left out.
 */
function layoutJointHandles(runtime, handles, width, height) {
  const { THREE, camera, modelGroup } = runtime;
  camera.updateMatrixWorld();
  modelGroup.updateMatrixWorld();
  const scratch = new THREE.Vector3();
  const toWorld = (point) => scratch.fromArray(point).applyMatrix4(modelGroup.matrixWorld).toArray();
  const toWorldDirection = (direction) => scratch.fromArray(direction).transformDirection(modelGroup.matrixWorld).toArray();
  const inFront = (point) => scratch.fromArray(point).applyMatrix4(camera.matrixWorldInverse).z < -camera.near;
  const project = (point) => {
    scratch.fromArray(point).project(camera);
    return [((scratch.x + 1) * width) / 2, ((1 - scratch.y) * height) / 2];
  };
  const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).toArray();
  const layouts = [];
  for (const handle of handles) {
    const pivot = toWorld(handle.pivot);
    const axis = toWorldDirection(handle.axis);
    const direction = handleArmDirection({ kind: handle.kind, pivot, axis, toward: handle.toward ? toWorld(handle.toward) : null });
    if (!direction || !inFront(pivot)) continue;
    // Measured, not derived from the lens: a short step across the view at the
    // pivot's depth, so the arm is JOINT_HANDLE_ARM_PX long under any projection.
    const probe = Math.max(scratch.fromArray(pivot).distanceTo(camera.position) * 0.01, 1e-6);
    const pivotPx = project(pivot);
    const probePx = project(add(pivot, scale(right, probe)));
    const pixelsPerUnit = Math.hypot(probePx[0] - pivotPx[0], probePx[1] - pivotPx[1]) / probe;
    if (!(pixelsPerUnit > 0)) continue;
    const reach = JOINT_HANDLE_ARM_PX / pixelsPerUnit;
    const knob = add(pivot, scale(direction, reach));
    if (!inFront(knob)) continue;
    const limited = Number.isFinite(handle.min) && Number.isFinite(handle.max);
    let guide = [];
    let guideClosed = false;
    if (handle.kind === "prismatic") {
      // The knob's own travel: the limit range, carried out to the end of the arm.
      guide = limited ? [handle.min, handle.max].map((value) => add(knob, scale(axis, value - handle.value))) : [];
    } else {
      guideClosed = !limited || handle.max - handle.min >= 360;
      guide = arcPoints({
        pivot, axis, direction, radius: reach,
        fromDeg: guideClosed ? 0 : handle.min - handle.value,
        toDeg: guideClosed ? 360 : handle.max - handle.value
      });
    }
    layouts.push({
      id: handle.id, handle, pivot, axis, reach, pivotPx,
      knobPx: project(knob),
      guidePx: guide.map((point) => (inFront(point) ? project(point) : null)),
      guideClosed
    });
  }
  return { layouts, project };
}

/**
 * The Pose tool in the viewport: a knob per joint, drawn over the scene, that
 * drags the joint through `handle.onChange`.
 *
 * `handles` is the adapters' list for the CURRENT pose; the hook lives exactly as
 * long as the tool. Nothing here is React state: the list lands in a ref, a frame loop
 * repaints when the camera, the list or the pointer changed, and the label is
 * written straight into its element. A press on a knob is taken before
 * OrbitControls sees it (capture phase, above the WebGL canvas) and the controls
 * are switched off for as long as the knob is held; any other press is left alone.
 */
export function useJointHandles({ handles, runtimeRef, hostRef, canvasRef, labelRef, layoutSeamRef, viewerReadyTick }) {
  const handlesRef = useRef(handles);
  handlesRef.current = handles;

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    const label = labelRef.current;
    const runtime = runtimeRef.current;
    if (!host || !canvas || !label || !runtime?.camera) return undefined;

    let frameId = 0;
    let paintedKey = "";
    let paintedHandles = null;
    let hoverId = "";
    // { id, pointerId, grab, value, pending, controlsWereEnabled }
    let drag = null;
    let layout = { layouts: [], project: () => [0, 0] };

    const size = () => ({ width: host.clientWidth || 1, height: host.clientHeight || 1 });
    const relayout = () => {
      const { width, height } = size();
      layout = layoutJointHandles(runtimeRef.current, handlesRef.current, width, height);
      return layout;
    };
    layoutSeamRef.current = () => relayout().layouts.map(({ id, knobPx, pivotPx, handle }) => (
      { id, x: knobPx[0], y: knobPx[1], pivotX: pivotPx[0], pivotY: pivotPx[1], value: handle.value }
    ));

    const paint = () => {
      frameId = window.requestAnimationFrame(paint);
      const live = runtimeRef.current;
      if (!live?.camera) return;
      const { width, height } = size();
      const dpr = window.devicePixelRatio || 1;
      live.camera.updateMatrixWorld();
      // Everything a repaint depends on; an idle viewport compares and returns.
      const key = [
        width, height, dpr, hoverId, drag?.id || "", live.camera.zoom,
        live.camera.matrixWorld.elements.join(), live.camera.projectionMatrix.elements.join(),
        live.modelGroup.position.toArray().join()
      ].join("|");
      if (key === paintedKey && paintedHandles === handlesRef.current) return;
      paintedKey = key;
      paintedHandles = handlesRef.current;
      relayout();
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      const context = canvas.getContext("2d");
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);
      const activeId = drag?.id || hoverId;
      drawJointHandles(context, layout.layouts, { activeId, quiet: layout.layouts.length > QUIET_HANDLE_COUNT });
      const labelled = layout.layouts.find((item) => item.id === activeId);
      label.hidden = !labelled;
      if (labelled) {
        label.textContent = `${labelled.handle.label}  ${formatJointHandleValue(labelled.handle.value, labelled.handle.unit)}`;
        label.style.transform = `translate(${Math.round(labelled.knobPx[0] + LABEL_OFFSET_PX)}px, ${Math.round(labelled.knobPx[1] - LABEL_OFFSET_PX)}px) translateY(-100%)`;
      }
    };

    const localPoint = (event) => {
      const rect = host.getBoundingClientRect();
      return [event.clientX - rect.left, event.clientY - rect.top];
    };
    // Its own raycaster: the runtime's belongs to picking, mid-gesture state included.
    const raycaster = new runtime.THREE.Raycaster();
    const ndc = new runtime.THREE.Vector2();
    const sampleAt = (point) => {
      const { width, height } = size();
      raycaster.setFromCamera(ndc.set((point[0] / width) * 2 - 1, 1 - (point[1] / height) * 2), runtimeRef.current.camera);
      const { origin, direction } = raycaster.ray;
      return { ray: { origin: origin.toArray(), direction: direction.toArray() }, pointer: point, project: layout.project };
    };
    const setHover = (id) => {
      hoverId = id;
      host.style.cursor = drag ? "grabbing" : id ? "grab" : "";
    };

    const flush = () => {
      if (!drag?.pending) return;
      drag.pending = false;
      // The list is rebuilt per pose; the closure that writes must be this pose's.
      handlesRef.current.find((handle) => handle.id === drag.id)?.onChange(drag.value);
    };
    const endDrag = () => {
      if (!drag) return;
      flush();
      const live = runtimeRef.current;
      if (live?.controls) live.controls.enabled = drag.controlsWereEnabled;
      if (host.hasPointerCapture?.(drag.pointerId)) host.releasePointerCapture(drag.pointerId);
      drag = null;
      setHover(hoverId);
    };

    const handlePointerDown = (event) => {
      // Left button or a finger, unmodified: Shift/Ctrl/Cmd+drag is the camera's pan.
      if (drag || event.button !== 0 || event.shiftKey || event.ctrlKey || event.metaKey) return;
      const point = localPoint(event);
      const hit = jointHandleAt(relayout().layouts, point, event.pointerType === "touch" ? JOINT_HANDLE_TOUCH_HIT_PX : JOINT_HANDLE_HIT_PX);
      const grab = hit ? beginJointDrag({ ...hit.handle, pivot: hit.pivot, axis: hit.axis, reach: hit.reach }, sampleAt(point)) : null;
      if (!grab) return;
      event.preventDefault();
      event.stopPropagation();
      const controls = runtimeRef.current.controls;
      drag = { id: hit.id, pointerId: event.pointerId, grab, value: grab.value, pending: false, controlsWereEnabled: controls?.enabled !== false };
      if (controls) controls.enabled = false;
      host.setPointerCapture?.(event.pointerId);
      setHover(hit.id);
    };
    const handlePointerMove = (event) => {
      if (drag) {
        if (event.pointerId !== drag.pointerId) return;
        event.preventDefault();
        event.stopPropagation();
        drag.grab = advanceJointDrag(drag.grab, sampleAt(localPoint(event)));
        drag.value = drag.grab.value;
        // One write per painted frame, however fast the pointer reports.
        if (!drag.pending) {
          drag.pending = true;
          window.requestAnimationFrame(flush);
        }
        return;
      }
      // A camera gesture is under way: no hover, and no claim on the event.
      if (event.buttons !== 0 || event.pointerType === "touch") return;
      const hit = jointHandleAt(layout.layouts, localPoint(event), JOINT_HANDLE_HIT_PX);
      if (hit) event.stopPropagation();
      if ((hit?.id || "") !== hoverId) setHover(hit?.id || "");
    };
    const handlePointerEnd = (event) => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      event.stopPropagation();
      endDrag();
    };
    const handlePointerLeave = () => {
      if (!drag && hoverId) setHover("");
    };

    host.addEventListener("pointerdown", handlePointerDown, true);
    host.addEventListener("pointermove", handlePointerMove, true);
    host.addEventListener("pointerup", handlePointerEnd, true);
    host.addEventListener("pointercancel", handlePointerEnd, true);
    host.addEventListener("lostpointercapture", handlePointerEnd, true);
    host.addEventListener("pointerleave", handlePointerLeave);
    frameId = window.requestAnimationFrame(paint);

    return () => {
      // Leaving the tool with a knob held must hand the camera back.
      endDrag();
      window.cancelAnimationFrame(frameId);
      host.removeEventListener("pointerdown", handlePointerDown, true);
      host.removeEventListener("pointermove", handlePointerMove, true);
      host.removeEventListener("pointerup", handlePointerEnd, true);
      host.removeEventListener("pointercancel", handlePointerEnd, true);
      host.removeEventListener("lostpointercapture", handlePointerEnd, true);
      host.removeEventListener("pointerleave", handlePointerLeave);
      host.style.cursor = "";
      label.hidden = true;
      canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
      layoutSeamRef.current = null;
    };
  }, [runtimeRef, hostRef, canvasRef, labelRef, layoutSeamRef, viewerReadyTick]);
}
