import { useEffect, useRef } from "react";
import { Check, X } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { cn } from "@hardcore/ui/utils";
import { measureModelOffsetFromRuntime } from "../../scene/useStepPicking.js";
import { AnnotationBody } from "./StepAnnotations.jsx";

// Annotations on the model itself: a numbered dot where each one was made, and its card when
// the dot is pressed. The dots are HTML over the canvas, moved every frame to where their
// anchors project (as the Position tool's knobs are), so they follow the camera without a
// React render per frame.

const CARD_WIDTH_PX = 288;
const EDGE_MARGIN_PX = 12;

/**
 * Where an anchor is on screen now, or null when it is behind the camera. `facing` is false
 * when the anchor's face points away from the camera: its dot is on the far side.
 */
export function projectAnnotationAnchor(runtime, anchor, width, height) {
  const { THREE, camera } = runtime || {};
  if (!THREE || !camera || !anchor?.point) return null;
  const [dx, dy, dz] = measureModelOffsetFromRuntime(runtime);
  const world = new THREE.Vector3(anchor.point[0] + dx, anchor.point[1] + dy, anchor.point[2] + dz);
  camera.updateMatrixWorld();
  if (world.clone().applyMatrix4(camera.matrixWorldInverse).z >= -camera.near) return null;
  let facing = true;
  if (anchor.normal) {
    const toCamera = camera.position.clone().sub(world);
    facing = toCamera.dot(new THREE.Vector3(...anchor.normal)) >= 0;
  }
  const ndc = world.project(camera);
  return { x: ((ndc.x + 1) * width) / 2, y: ((1 - ndc.y) * height) / 2, facing };
}

/**
 * The bar over the model while there are annotations to add: "3 annotations · Add to chat · ×",
 * as Codex's comment bar is. Adding puts every one not yet added into the chat box, in one go;
 * the cross clears them all.
 */
function AnnotationsBar({ pending, total, canAddToChat, onAddToChat, onClear }) {
  if (!total) return null;
  const count = pending || total;
  const label = `${count} ${count === 1 ? "annotation" : "annotations"}`;
  return (
    <div className="pointer-events-none absolute inset-x-0 top-3 z-30 flex justify-center">
      <div role="toolbar" aria-label="Annotations" onPointerDown={event => event.stopPropagation()}
        className="pointer-events-auto flex items-center gap-1 rounded-full border bg-background/95 py-1 pr-1 pl-3.5 text-[13px] shadow-lg shadow-black/15 backdrop-blur">
        <span className="tabular-nums">{pending ? label : `${label} added`}</span>
        {pending ? (
          <Button type="button" size="sm" disabled={!canAddToChat} onClick={() => void onAddToChat()}
            className="ml-1 h-7 rounded-full bg-blue-500 px-3 text-[13px] text-white hover:bg-blue-500/90">
            Add to chat
          </Button>
        ) : <Check className="ml-0.5 size-3.5 text-muted-foreground" aria-hidden="true" />}
        <Button type="button" variant="ghost" size="icon-xs" className="size-7 rounded-full text-muted-foreground"
          aria-label="Clear annotations" onClick={onClear}>
          <X className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}

export default function AnnotationPins({ viewport, annotations, openId, onOpenChange, canAddToChat, onAddToChat, onClear, ...body }) {
  const pinRefs = useRef(new Map());
  const annotationsRef = useRef(annotations);
  annotationsRef.current = annotations;
  const { runtimeRef, hostRef } = viewport;

  useEffect(() => {
    let frame = 0;
    const place = () => {
      frame = window.requestAnimationFrame(place);
      const runtime = runtimeRef.current;
      const host = hostRef.current;
      if (!runtime || !host) return;
      const width = host.clientWidth;
      const height = host.clientHeight;
      for (const annotation of annotationsRef.current) {
        const element = pinRefs.current.get(annotation.id);
        if (!element) continue;
        const at = projectAnnotationAnchor(runtime, annotation.anchor, width, height);
        const onScreen = at && at.x >= 0 && at.y >= 0 && at.x <= width && at.y <= height;
        element.hidden = !onScreen;
        if (!onScreen) continue;
        element.style.transform = `translate(${Math.round(at.x)}px, ${Math.round(at.y)}px)`;
        element.dataset.facing = String(at.facing);
        // The card opens toward the side there is room on.
        element.dataset.side = at.x + CARD_WIDTH_PX + EDGE_MARGIN_PX > width ? "left" : "right";
      }
    };
    place();
    return () => window.cancelAnimationFrame(frame);
  }, [runtimeRef, hostRef]);

  const placed = annotations.filter(annotation => annotation.anchor);
  if (!placed.length) return null;
  return (
    <div className="pointer-events-none absolute inset-0 z-20 overflow-hidden" data-annotation-pins="">
      <AnnotationsBar pending={annotations.filter(annotation => !annotation.sent).length} total={annotations.length}
        canAddToChat={canAddToChat} onAddToChat={onAddToChat} onClear={onClear} />
      {annotations.map((annotation, index) => {
        if (!annotation.anchor) return null;
        const open = openId === annotation.id;
        return (
          <div key={annotation.id} ref={element => {
            // Hidden until the frame loop has placed it; after that the loop alone owns it.
            if (element && !pinRefs.current.has(annotation.id)) { element.hidden = true; pinRefs.current.set(annotation.id, element); }
            else if (!element) pinRefs.current.delete(annotation.id);
          }}
            className="group/pin absolute left-0 top-0" data-annotation-pin={annotation.id} data-open={open}
            // A press on a dot or its card is not a press on the model: no pick, no orbit.
            onPointerDown={event => event.stopPropagation()} onDoubleClick={event => event.stopPropagation()}
            onContextMenu={event => event.stopPropagation()}>
            <button type="button" aria-label={`Annotation ${index + 1}`} aria-expanded={open}
              onClick={() => onOpenChange(open ? null : annotation.id)}
              className={cn(
                "pointer-events-auto absolute flex size-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-background text-[11px] font-semibold tabular-nums shadow-md shadow-black/30 transition-[transform,opacity]",
                "hover:scale-110 group-data-[facing=false]/pin:opacity-45",
                annotation.sent ? "bg-muted-foreground text-background" : "bg-blue-500 text-white",
                open && "scale-110 ring-2 ring-blue-500/40 ring-offset-1 ring-offset-background"
              )}>
              {index + 1}
            </button>
            {open ? (
              <div role="dialog" aria-label={`Annotation ${index + 1} details`} style={{ width: CARD_WIDTH_PX }}
                onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); onOpenChange(null); } }}
                className="pointer-events-auto absolute top-0 -translate-y-1/2 rounded-lg border bg-popover p-2 text-popover-foreground shadow-lg group-data-[side=right]/pin:left-5 group-data-[side=left]/pin:right-5">
                <AnnotationBody annotation={annotation} index={index} {...body}
                  onSelect={() => body.onSelect(annotation)} onEdit={text => body.onEdit(annotation.id, text)}
                  onRemove={() => body.onRemove(annotation.id)}
                  actions={<Button type="button" variant="ghost" size="icon-xs" className="size-6 text-muted-foreground"
                    aria-label="Close" onClick={() => onOpenChange(null)}><X className="size-3.5" /></Button>} />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
