import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { annotationAt, highlighterMark, penMark, shapeMarks, textMark, withGroups } from "../../../../annotation/geometry.js";
import { DEFAULT_OVERLAY_ANNOTATION_COLOR } from "../../../../annotation/toolbar.jsx";
import { capturePointer } from "../../../../lib/pointerCapture.js";
import { annotationsOnScreen, projectAnnotations } from "./annotation3d.js";
import { TOUCH_HIT_PX } from "../../viewport/dom.js";
import { useI18n } from "@text-to-cad/ui/i18n";

// Someone who took up a drawing tool came to draw: Pencil opens on the pen, Shapes on the rectangle, each in the neon red
// (the highlighter, in the session's yellow).
export const CAD_ANNOTATION_DEFAULTS = Object.freeze({
  styles: Object.freeze({ pen: Object.freeze({ color: DEFAULT_OVERLAY_ANNOTATION_COLOR }), shapes: Object.freeze({ color: DEFAULT_OVERLAY_ANNOTATION_COLOR }) }),
});

const SHAPES = new Set(["line", "arrow", "rectangle", "ellipse"]);
const ERASER_RADIUS = 8;
// A finger's eraser is a fingertip across (`TOUCH_HIT_PX`).
const eraserRadius = pointerType => pointerType === "touch" ? TOUCH_HIT_PX : ERASER_RADIUS;
const FONT_PX = Object.freeze({ 1: 16, 2: 20, 4: 28 });
const fontOf = px => `500 ${px}px ui-sans-serif, system-ui, sans-serif`;

// A mark's path on the preview canvas: its points, at its width (a pen's, point by point).
function paintMark(context, mark) {
  context.save();
  context.globalAlpha = mark.opacity ?? 1;
  context.strokeStyle = mark.color;
  context.fillStyle = mark.color;
  context.lineCap = "round";
  context.lineJoin = "round";
  if (mark.kind === "area") {
    context.beginPath();
    mark.outline.forEach((point, index) => (index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y)));
    context.closePath();
    context.fill();
  } else if (mark.widths) {
    for (let index = 1; index < mark.points.length; index += 1) {
      context.lineWidth = mark.width * (mark.widths[index - 1] + mark.widths[index]) / 2;
      context.beginPath();
      context.moveTo(mark.points[index - 1].x, mark.points[index - 1].y);
      context.lineTo(mark.points[index].x, mark.points[index].y);
      context.stroke();
    }
  } else {
    context.lineWidth = mark.width;
    context.beginPath();
    mark.points.forEach((point, index) => (index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y)));
    context.stroke();
  }
  context.restore();
}
// Ink already in the model, outlined where it falls on the screen: what the eraser is about to take.
function paintOutline(context, ink, { color }) {
  context.save();
  context.strokeStyle = color;
  context.lineWidth = Math.max(2, ink.width + 4);
  context.globalAlpha = 0.45;
  context.lineCap = "round";
  context.lineJoin = "round";
  context.beginPath();
  const path = ink.closed || ink.kind !== "stroke" ? [...ink.points, ink.points[0]] : ink.points;
  path.forEach((point, index) => (index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y)));
  context.stroke();
  context.restore();
}

/**
 * The drawing tools' surface over the viewport (Pencil and Shapes): every tool's gesture, its ink previewed as it is made (on a
 * canvas of its own, in screen space) and put into the model as it ends (`annotation3d.js`): the pen, the highlighter, the
 * line, the arrow, the rectangle and the ellipse drawn; text written in place; the eraser dragged
 * over ink. Every mark lies on the surface it starts on (`annotation3d.js`'s `levelOf`: that
 * surface's plane), each point on the surface under it or on that plane, by the session's `placement`. What each
 * mark touches comes from `touchesAt` (the renderer's `inkTouches`). All of it works on the whole annotation, whatever view each piece
 * was drawn from. Picking ink is the viewer's Select's, not Annotate's (`RendererShell.jsx`); ink Select
 * picked is restyled on its selection's bar, and Delete deletes it here too.
 * The camera is the person's between strokes: the wheel zooms, a right or middle drag orbits (the
 * press goes on to the view as its own), and while Space is held the pointer is the view's. ⌘Z / ⇧⌘Z are the viewer's (its one history). Each mark names
 * the view it was put down in (`viewOf`, the session's `noteView`): a prompt carries every view its
 * ink was drawn in.
 *
 * A view that is no 3D scene (a flat one) hands its own `surface`: `place(marks, size)`, the marks
 * put down as the session keeps them; `onScreen(items, size)`, the ink as it falls on the screen now;
 * and `view()`, the element a right or middle press and the wheel go on to. Without one, ink goes
 * into the viewport's scene (`runtimeRef`).
 *
 * @param {{ annotation: import("../../../../annotation/session.js").AnnotationSession, runtimeRef?: { current: any },
 *   viewOf?: (() => object | null) | null, touchesAt?: ((clientX: number, clientY: number) => { part: string, ref?: string }[]) | null, surface?: { place(marks: object[], size: { width: number, height: number }): object[],
 *     onScreen(items: readonly object[], size: { width: number, height: number }): object[], view(): Element | null } | null }} props
 */
export default function AnnotationOverlay({ annotation, runtimeRef = null, viewOf = null, touchesAt = null, surface = null }) {
  const { t } = useI18n();
  const root = useRef(null);
  const canvas = useRef(null);
  const gesture = useRef(null);
  // Marks just put into the model, still previewed until the scene has drawn them.
  const landing = useRef(null);
  const [text, setText] = useState(null);
  // Space held: the pointer is the view's, to orbit, as a design tool's hand is.
  const [passing, setPassing] = useState(false);
  const textRef = useRef(text);
  textRef.current = text;
  const annotationRef = useRef(annotation);
  annotationRef.current = annotation;
  const style = { color: annotation.style.color, width: annotation.style.strokeWidth };
  const styleRef = useRef(style);
  styleRef.current = style;
  // The freehand gesture's mark: the pen's, tapered by pressure, or the highlighter's, broad and translucent.
  const inkOf = current => (current.highlight ? highlighterMark(current.points, styleRef.current) : penMark(current.points, styleRef.current, current.pressures));

  const size = () => ({ width: root.current?.clientWidth || 0, height: root.current?.clientHeight || 0 });
  const point = event => {
    const rect = root.current.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };
  const surfaceRef = useRef(surface);
  surfaceRef.current = surface;
  const onScreen = () => (surfaceRef.current ? surfaceRef.current.onScreen(annotationRef.current.items, size())
    : annotationsOnScreen(runtimeRef.current, annotationRef.current.items, size()));
  // Where a press or a wheel that is the view's goes on to: the flat view's own element, or the scene's canvas.
  const viewElement = () => (surfaceRef.current ? surfaceRef.current.view() : runtimeRef?.current?.renderer?.domElement) || null;
  const viewOfRef = useRef(viewOf);
  viewOfRef.current = viewOf;
  // The view ink is going down in, as the session labels it.
  const viewNow = () => annotationRef.current.noteView?.(viewOfRef.current?.() ?? null);
  const touchesAtRef = useRef(touchesAt);
  touchesAtRef.current = touchesAt;
  // Each mark put down lies on the surface it starts on (`annotation3d.js`), and names what it touches.
  const put = marks => {
    const runtime = runtimeRef?.current, session = annotationRef.current, flat = surfaceRef.current;
    if ((!flat && !runtime) || !marks.length) return;
    const view = viewNow();
    const placed = marks.map(mark => ({ ...mark, ...(view ? { view } : {}) }));
    if (flat) { session.add(flat.place(placed, size())); return; }
    const rect = root.current.getBoundingClientRect(), lookup = touchesAtRef.current;
    session.add(projectAnnotations(runtime, placed, size(), { placement: session.style.placement,
      touchesAt: lookup ? at => lookup(rect.left + at.x, rect.top + at.y) : null }));
  };

  // A mark drawn stays on the preview until the frame after the one that draws it in the model,
  // so it never blinks out between the two.
  const land = marks => {
    put(marks);
    landing.current = marks;
    globalThis.requestAnimationFrame?.(() => globalThis.requestAnimationFrame?.(() => {
      if (landing.current !== marks) return;
      landing.current = null;
      paint();
    }));
  };

  // The preview: the gesture in progress.
  const paint = useCallback(() => {
    const element = canvas.current, host = root.current;
    if (!element || !host) return;
    const ratio = globalThis.devicePixelRatio || 1;
    const width = host.clientWidth, height = host.clientHeight;
    if (element.width !== Math.round(width * ratio) || element.height !== Math.round(height * ratio)) {
      element.width = Math.round(width * ratio);
      element.height = Math.round(height * ratio);
    }
    const context = element.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    const current = gesture.current, session = annotationRef.current;
    for (const mark of landing.current || []) paintMark(context, mark);
    if (!current) return;
    if (current.kind === "pen") {
      const mark = inkOf(current);
      if (mark) paintMark(context, mark);
    } else if (current.kind === "shape") {
      for (const mark of shapeMarks(current.tool, current.from, current.to, styleRef.current)) paintMark(context, mark);
    } else if (current.kind === "erase") {
      const erasing = new Set(withGroups([...current.hits], session.items));
      for (const ink of current.screen.filter(item => erasing.has(item.id))) paintOutline(context, ink, { color: "#ffffff" });
      const last = current.path[current.path.length - 1];
      context.save();
      context.strokeStyle = "rgba(255,255,255,0.8)";
      context.lineWidth = 1;
      context.beginPath();
      context.arc(last.x, last.y, current.radius ?? ERASER_RADIUS, 0, Math.PI * 2);
      context.stroke();
      context.restore();
    }
  }, [runtimeRef]);
  useLayoutEffect(() => { paint(); }, [paint, annotation.items]);

  // The text being written closes: kept (put down) or dropped (Escape). Closed by a key or a press on
  // the surface, the keyboard goes back to the surface, for Space and ⌘Z; closed by focus going elsewhere, it
  // stays there.
  const closeText = (keep, { refocus = true } = {}) => {
    const current = textRef.current;
    textRef.current = null;
    setText(null);
    if (keep) commitText(current);
    if (refocus) root.current?.focus({ preventScroll: true });
  };
  // Written text, measured as it is drawn, put down as a text mark where it was written.
  const commitText = current => {
    if (!current?.value.trim()) return;
    const { fontPx } = current;
    const lines = current.value.trim().split("\n");
    const measure = globalThis.document?.createElement("canvas")?.getContext("2d");
    if (measure) measure.font = fontOf(fontPx);
    const width = Math.max(...lines.map(line => measure?.measureText(line).width ?? line.length * fontPx * 0.55));
    const mark = textMark(current.value, current.at, { width, height: lines.length * fontPx * 1.25 }, { color: current.color, fontPx });
    if (mark) put([mark]);
  };

  // A right or middle press is the view's: it goes on to the canvas as the press that orbits, and the
  // canvas takes the pointer from there.
  const handToView = event => {
    const target = viewElement();
    if (!target) return;
    event.preventDefault();
    target.dispatchEvent(new PointerEvent("pointerdown", { pointerId: event.pointerId, pointerType: event.pointerType, isPrimary: event.isPrimary,
      clientX: event.clientX, clientY: event.clientY, screenX: event.screenX, screenY: event.screenY, button: 0, buttons: 1, bubbles: true, cancelable: true }));
  };
  const onPointerDown = event => {
    if (event.button === 1 || event.button === 2) { handToView(event); return; }
    if (event.button !== 0) return;
    const session = annotationRef.current, at = point(event);
    if (textRef.current) { closeText(true); return; }
    root.current.focus({ preventScroll: true });
    capturePointer(event.currentTarget, event.pointerId);
    const pressure = event.pointerType === "pen" ? event.pressure : null;
    if (session.tool === "freedraw") gesture.current = { kind: "pen", points: [at], pressures: pressure == null ? null : [pressure] };
    else if (session.tool === "highlighter") gesture.current = { kind: "pen", highlight: true, points: [at], pressures: null };
    else if (SHAPES.has(session.tool)) gesture.current = { kind: "shape", tool: session.tool, from: at, to: at };
    else if (session.tool === "eraser") {
      const screen = onScreen();
      const radius = eraserRadius(event.pointerType);
      gesture.current = { kind: "erase", screen, path: [at], radius, hits: new Set(annotationAt(at, screen, radius).map(ink => ink.id)) };
    } else if (session.tool === "text") {
      setText({ at, value: "", color: session.style.color, fontPx: FONT_PX[session.style.strokeWidth] ?? 20 });
    }
    paint();
  };
  const onPointerMove = event => {
    const current = gesture.current;
    if (!current) return;
    const at = point(event);
    if (current.kind === "pen") {
      current.points.push(at);
      if (current.pressures) current.pressures.push(event.pressure);
    } else if (current.kind === "shape") current.to = at;
    else if (current.kind === "erase") {
      current.path.push(at);
      for (const ink of annotationAt(at, current.screen, current.radius)) current.hits.add(ink.id);
    }
    paint();
  };
  const onPointerUp = () => {
    const current = gesture.current, session = annotationRef.current;
    gesture.current = null;
    if (current?.kind === "pen") { const mark = inkOf(current); if (mark) land([mark]); }
    else if (current?.kind === "shape") land(shapeMarks(current.tool, current.from, current.to, styleRef.current));
    else if (current?.kind === "erase") session.remove(withGroups([...current.hits], session.items));
    paint();
  };
  // The surface takes the keyboard itself, on the press: the mousedown after it would focus the
  // surface again and blur the text just opened there, closing it before a key is typed.
  const onMouseDown = event => { if (event.target === event.currentTarget) event.preventDefault(); };
  const onKeyDown = event => {
    const session = annotationRef.current;
    if ((event.key === "Delete" || event.key === "Backspace") && session.selected.length) { event.preventDefault(); session.remove(session.selected); }
    else if (event.key === "Escape" && session.selected.length) { event.preventDefault(); session.select([]); }
    else if (event.key === " " && !event.repeat && !gesture.current) { event.preventDefault(); setPassing(true); }
  };
  const onKeyUp = event => { if (event.key === " ") setPassing(false); };
  // The wheel is the camera's, as it is outside Annotate.
  const onWheel = event => {
    const target = viewElement();
    target?.dispatchEvent(new WheelEvent("wheel", { deltaX: event.deltaX, deltaY: event.deltaY, deltaZ: event.deltaZ, deltaMode: event.deltaMode,
      clientX: event.clientX, clientY: event.clientY, ctrlKey: event.ctrlKey, shiftKey: event.shiftKey, metaKey: event.metaKey, bubbles: true, cancelable: true }));
  };

  return <div ref={root} tabIndex={-1} data-cad-annotation-overlay="" data-annotation-tool={annotation.tool} data-passing={passing ? "" : undefined}
    className="absolute inset-0 z-10 outline-none"
    style={{ pointerEvents: passing ? "none" : "auto", cursor: annotation.tool === "text" ? "text" : "crosshair", touchAction: "none" }}
    onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
    onMouseDown={onMouseDown} onKeyDown={onKeyDown} onKeyUp={onKeyUp} onBlur={() => setPassing(false)} onWheel={onWheel}
    onContextMenu={event => event.preventDefault()}>
    <canvas ref={canvas} className="pointer-events-none absolute inset-0 h-full w-full" />
    {text ? <textarea autoFocus aria-label={t("annotate.tool.text")} value={text.value} rows={1}
      onChange={event => setText(current => current && { ...current, value: event.target.value })}
      onKeyDown={event => {
        event.stopPropagation();
        if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); closeText(true); }
        else if (event.key === "Escape") { event.preventDefault(); closeText(false); }
      }}
      onBlur={() => closeText(true, { refocus: false })} onPointerDown={event => event.stopPropagation()}
      className="absolute resize-none overflow-hidden border-0 bg-transparent p-0 outline-none [field-sizing:content]"
      style={{ left: text.at.x, top: text.at.y, color: text.color, font: fontOf(text.fontPx), lineHeight: 1.25, minWidth: "1ch" }} /> : null}
  </div>;
}
