import { memo, useCallback, useEffect, useRef } from "react";
import { X } from "lucide-react";
import { projectWorldPointToClient } from "@hardcore/core/lib/viewer/measureRuler.js";
import { Button } from "@hardcore/ui/primitives/button";
import { Popover, PopoverContent, PopoverTrigger } from "@hardcore/ui/primitives/popover";
import { cn } from "@hardcore/ui/utils";
import { measureModelOffsetFromRuntime } from "../../scene/useStepPicking.js";
import { AnnotationBody } from "./StepAnnotations.jsx";

// Annotations on the model itself: a numbered dot where each one was made, and its card when the
// dot is pressed. The dots are HTML over the canvas, moved by a frame loop to where their anchors
// project (as the Position tool's knobs are), so they follow the camera without a React render per
// frame. A card is a popover anchored to its dot: it stays inside the viewport and follows the dot.

/** Where an anchor is on screen now, or null when it is behind the camera or off the view. */
function projectAnchor(anchor, { camera, offset, width, height }) {
  const world = anchor.point.map((value, axis) => value + offset[axis]);
  const at = projectWorldPointToClient(world, camera, { left: 0, top: 0, width, height });
  if (!at || at.x < 0 || at.y < 0 || at.x > width || at.y > height) return null;
  // A dot on a face turned away from the camera is on the far side of the model.
  const normal = anchor.normal;
  const facing = !normal || normal.reduce((sum, value, axis) => sum + value * (camera.position.getComponent(axis) - world[axis]), 0) >= 0;
  return { x: Math.round(at.x), y: Math.round(at.y), facing };
}

const Pin = memo(function Pin({ annotation, index, open, register, host, onOpenChange, onSelect, onEdit, onRemove }) {
  const ref = useCallback(element => register(annotation.id, element), [register, annotation.id]);
  return (
    <div ref={ref} className="group/pin absolute left-0 top-0" data-annotation-pin={annotation.id} data-open={open}
      // A press on a dot or its card is not a press on the model: no pick, no orbit.
      onPointerDown={event => event.stopPropagation()} onDoubleClick={event => event.stopPropagation()}
      onContextMenu={event => event.stopPropagation()}>
      <Popover open={open} onOpenChange={next => onOpenChange(next ? annotation.id : null)}>
        <PopoverTrigger asChild>
          <button type="button" aria-label={`Annotation ${index + 1}`}
            className={cn(
              "pointer-events-auto absolute flex size-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-background bg-blue-500 text-[11px] font-semibold text-white tabular-nums shadow-md shadow-black/30 transition-[transform,opacity]",
              "hover:scale-110 group-data-[facing=false]/pin:opacity-45",
              open && "scale-110 ring-2 ring-blue-500/40 ring-offset-1 ring-offset-background"
            )}>
            {index + 1}
          </button>
        </PopoverTrigger>
        <PopoverContent container={host} collisionBoundary={host} collisionPadding={12} updatePositionStrategy="always"
          side="right" sideOffset={12} aria-label={`Annotation ${index + 1} details`}
          className="w-72 p-2" onOpenAutoFocus={event => event.preventDefault()}
          // Escape in the note's edit box cancels the edit; only outside it does it close the card.
          onEscapeKeyDown={event => { if (event.target?.tagName === "TEXTAREA") event.preventDefault(); }}>
          <AnnotationBody annotation={annotation} index={index}
            onSelect={() => onSelect(annotation)} onEdit={text => onEdit(annotation.id, text)} onRemove={() => onRemove(annotation.id)}
            actions={<Button type="button" variant="ghost" size="icon-xs" className="size-6 text-muted-foreground"
              aria-label="Close" onClick={() => onOpenChange(null)}><X className="size-3.5" /></Button>} />
        </PopoverContent>
      </Popover>
    </div>
  );
});

function AnnotationPins({ viewport, annotations, openId, onOpenChange, onSelect, onEdit, onRemove }) {
  const { runtimeRef, hostRef } = viewport;
  const annotationsRef = useRef(annotations);
  annotationsRef.current = annotations;
  const pins = useRef(new Map());
  // A new dot starts hidden; the frame loop shows it where its anchor projects.
  const register = useCallback((id, element) => {
    if (!element) { pins.current.delete(id); return; }
    element.hidden = true;
    pins.current.set(id, { element, placed: "" });
  }, []);

  const shown = annotations.length > 0;
  useEffect(() => {
    if (!shown) return undefined;
    let frame = 0;
    const place = () => {
      frame = window.requestAnimationFrame(place);
      const runtime = runtimeRef.current;
      const host = hostRef.current;
      if (!runtime?.camera || !host) return;
      runtime.camera.updateMatrixWorld();
      const view = { camera: runtime.camera, offset: measureModelOffsetFromRuntime(runtime), width: host.clientWidth, height: host.clientHeight };
      for (const annotation of annotationsRef.current) {
        const pin = pins.current.get(annotation.id);
        if (!pin) continue;
        const at = projectAnchor(annotation.anchor, view);
        // The page is written only when a dot moves, turns away or leaves the view.
        const placed = at ? `${at.x},${at.y},${at.facing}` : "off";
        if (pin.placed === placed) continue;
        pin.placed = placed;
        pin.element.hidden = !at;
        if (!at) continue;
        pin.element.style.transform = `translate(${at.x}px, ${at.y}px)`;
        pin.element.dataset.facing = String(at.facing);
      }
    };
    place();
    return () => window.cancelAnimationFrame(frame);
  }, [shown, runtimeRef, hostRef]);

  if (!shown) return null;
  return (
    <div className="pointer-events-none absolute inset-0 z-20 overflow-hidden" data-annotation-pins="">
      {annotations.map((annotation, index) => (
        <Pin key={annotation.id} annotation={annotation} index={index} open={openId === annotation.id} register={register}
          host={hostRef.current} onOpenChange={onOpenChange} onSelect={onSelect} onEdit={onEdit} onRemove={onRemove} />
      ))}
    </div>
  );
}

export default memo(AnnotationPins);
