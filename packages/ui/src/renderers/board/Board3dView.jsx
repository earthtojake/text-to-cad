/**
 * A board in 3D: the 3D views' own viewport (`kit/shell/ShellViewport.jsx`: its camera, its gestures,
 * its keys, but no cube: the board's corner is its zoom pill in 3D as in 2D, which zooms this camera)
 * around the bare board (`@cad/core/lib/board3d/boardStage.js`: a slab cut to the
 * outline, its two faces the 2D drawer's pictures of the two sides). A lazy chunk of the board's view
 * (`BoardRenderer.jsx`): a board on screen in 2D loads no three.js.
 *
 * It is the board view's other canvas, not another view: it mounts in the same frame as the flat
 * canvas, and everything round it — the strip, the panel, the selection, the tools' sessions, Quick
 * Edit — is the board view's, unmounted by nothing. What it hands the board view (`handle`) is what the
 * flat canvas does: where a pane point lands on the board and how far a pick there reaches, the camera
 * Measure draws through, Annotate's surface, the framing and the capture. A tap and the pointer resting
 * are the board view's own handlers (`onTap`, `onHover`), through the 3D views' tap-or-drag
 * (`kit/tools/select/usePointerPick.js`); a drag turns the view.
 *
 * Its stage's background is the 2D canvas's colour (`plot2d/theme.js`'s `boardPalette`), so the board
 * sits on its canvas as it does in 2D. It opens on `opening.camera`: the 2D window head on, unseen
 * (`shown` false: see-through, and deaf to the pointer) over the flat canvas showing that same picture,
 * until its viewport has presented a frame of the board with its face drawn (the stage is `presentable`
 * only then); it then tells the board view (`onShown`), which shows it in place of the flat canvas in one
 * frame: no frame of the viewport's own cover, nor of the bare slab. (Opened on the camera a file was
 * left at in 3D, it is shown at once, its cover over the pane until that frame.) Drawn and shown, it eases
 * to `opening.then` (the camera this file was left at in 3D) or to Home's tilt, on the side the 2D view
 * showed (`opening.side`: a camera on the other side turned over to it, `boardFrame.js`'s `cameraOnSide`);
 * whether anybody has moved the camera since (`moved`: a hand on it, `kit/camera/cameraTouch.js`) is what
 * leaving 3D asks.
 *
 * Its parts stand on it (`@cad/core/lib/board3d/boardParts.js`): each footprint's 3D model, the STEP the
 * board's models table names (`models`, `GET …/models`) read by its document id through the engine
 * (`client.engineDocument`) four at a time, baked into one geometry a model shared by every placement of
 * it, in the model's authored colours; a see-through block where a named model is missing. A press on a
 * body in front of the face picks its part (`pickPart`: the filter's Footprints); the highlight and an
 * isolation (`bodyInk`) light and fade the bodies as the faces' overlay lights the copper. Shown or not is
 * the Layers tab's 3D models (`showModels`).
 */
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { boardPalette } from "@cad/core/lib/plot2d/index.js";
import { createBoardStage } from "@cad/core/lib/board3d/boardStage.js";
import { createBoardParts, createModelLoader } from "@cad/core/lib/board3d/boardParts.js";
import {
  BOARD_THICKNESS_MM, cameraOnSide, cameraTurnedOver, millimetresPerPixel, perspectiveHeadOn, planFromCamera, sheetToWorldMatrix, sideSeenAlong
} from "@cad/core/lib/board3d/boardFrame.js";
import { VIEWER_SCENE_SCALE } from "@cad/core/lib/viewer/sceneScale.js";
import { DEFAULT_VIEW_DIRECTION, WORLD_UP } from "../kit/camera/viewportCameraKit.js";
import ShellViewport from "../kit/shell/ShellViewport.jsx";
import DoubleClickFit from "../kit/shell/DoubleClickFit.jsx";
import { useStageViewport } from "../kit/shell/useStageViewport.js";
import { plainShellCamera, scopeShellCamera } from "../kit/shell/fileView.js";
import { cameraHands } from "../kit/camera/cameraTouch.js";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";

const SCALE = VIEWER_SCENE_SCALE.CAD;
// What the 3D views' tap-or-drag is handed for a scene: the pointer alone. A tap and a resting pointer are
// the board view's to pick (`onTap`, `onHover`: its `pickAt`, the bodies, then the face), once a frame;
// the kit's own pick of the stage would be a second raycast of every body for nothing.
const POINTER_ONLY = Object.freeze({ pick: () => null });

/**
 * @param {{ handle: { current: object | null }, viewerRef: { current: object | null }, modelKey: string,
 *   layout: object, outline: number[][][] | null, display: object, colorScheme: "light" | "dark",
 *   opening: { camera: object, then: object | null, home: boolean, side: "top" | "bottom", flat?: boolean }, projection: string, shown: boolean,
 *   pickAt(located: object): object | null, onTap(point: object, event: object): void, onHover(point: object | null, event: object | null): void,
 *   picking: boolean, overlay(ctx: CanvasRenderingContext2D, frame: object): boolean,
 *   onCamera(camera: object, side: "top" | "bottom"): void, onShown(): void }} props
 *   `shown`: the board view shows this canvas in place of the flat one (after `onShown`).
 */
export default function Board3dView({ handle, viewerRef, modelKey, layout, outline, thickness = BOARD_THICKNESS_MM, display, colorScheme, opening, projection, shown = false,
  pickAt, onTap, onHover, picking, overlay, onCamera, onShown, parts = null, models = null, client = null, showModels = true, bodyInk = null, pickPart = null }) {
  const live = useRef(null);
  live.current = { pickAt, onTap, onHover, overlay, onCamera, onShown, display, colorScheme, client, bodyInk, pickPart };
  // The viewport the 3D views' overlay is handed: its runtime, and the element its pointer events arrive on.
  const viewportRef = useRef(null);
  // A part's body the ray meets in front of the face it enters (null: none, or one the board hides).
  const bodiesRef = useRef(null);
  const bodyOn = ray => {
    const hit = bodiesRef.current?.pick(ray);
    if (!hit?.ref) return null;
    const face = stage.locate(ray);
    return face && face.distance < hit.distance - 1e-3 ? null : hit;
  };
  const stage = useMemo(() => createBoardStage(THREE, { layout, outline, thickness, theme: colorScheme,
    pickAt: located => live.current.pickAt(located),
    pickBody: ray => {
      const body = bodyOn(ray), hit = body ? live.current.pickPart?.(body.ref) : null;
      return hit ? { hit, point: body.point } : null;
    } }), [layout, outline, thickness]);
  useEffect(() => () => stage.dispose(), [stage]);

  // ---- the parts: bodies where their models are, blocks where they are missing ------------------
  // Held across the board's revisions (a new plot is a new stage): the models baked stay, and a revision
  // that moved a part moves its matrix; only the stage they stand on is new.
  const bodies = useMemo(() => createBoardParts(THREE, { thickness, theme: colorScheme }), [thickness]);
  bodiesRef.current = bodies;
  useEffect(() => () => bodies.dispose(), [bodies]);
  useEffect(() => {
    stage.object3D.add(bodies.object3D);
    render();
    return () => { stage.object3D.remove(bodies.object3D); };
  }, [stage, bodies]);
  const loader = useMemo(() => createModelLoader(THREE, {
    open: (document, options) => live.current.client.engineDocument(document, options),
    onModel: (key, baked) => { bodies.addModel(key, baked); render(); },
    onFailed: (key, reason) => { bodies.failModel(key, reason); render(); }
  }), [bodies]);
  useEffect(() => () => loader.dispose(), [loader]);
  useEffect(() => {
    bodies.setParts(parts || [], models);
    if (typeof live.current.client?.engineDocument === "function") loader.request(bodies.wanted());
    render();
  }, [bodies, loader, parts, models]);
  useEffect(() => { bodies.setVisible(showModels); render(); }, [bodies, showModels]);
  useEffect(() => { bodies.setTheme(colorScheme); render(); }, [bodies, colorScheme]);
  const runtime = () => viewportRef.current?.runtimeRef.current || null;

  // The view settings a viewport outside the shell needs: no grid, no floor, the 2D canvas's colour behind it.
  const { props, store } = useStageViewport({ appearance: colorScheme, scope: modelKey, viewRef: viewerRef,
    background: boardPalette(colorScheme).background, projection });
  useEffect(() => { if (store.getSnapshot().scene.view.camera.projection !== projection) store.patch({ camera: { projection } }); }, [store, projection]);

  // ---- the faces: the Display drawn, once a renderer can take it ----------------------------
  const [tick, setTick] = useState(0);
  // Each frame asked for also says what the faces hold, on the view's element, as the flat canvas says it
  // is settled (no render): the sides drawn, the texture megapixels and the last face's draw in milliseconds.
  const frameRef = useRef(null);
  // And what the parts hold: placements with a body, blocks, distinct models, their mesh megabytes, those still loading.
  const render = () => {
    const { drawnSides, texturePixels, faceMs } = stage.stats();
    const held = bodiesRef.current?.stats();
    const element = frameRef.current;
    if (element) Object.assign(element.dataset, { boardFaces: drawnSides.join(" "), boardTextureMp: (texturePixels / 1e6).toFixed(1), boardFaceMs: faceMs.toFixed(0),
      ...(held ? { boardBodies: String(held.bodies), boardBlocks: String(held.blocks), boardModels: String(held.models),
        boardMeshMb: (held.bytes / 1e6).toFixed(2), boardModelsWaiting: String(held.waiting), boardModelsFailed: String(held.failed),
        ...(held.failure ? { boardModelFailure: held.failure.slice(0, 200) } : {}) } : {}) });
    runtime()?.requestRender?.();
  };
  useEffect(() => {
    const now = runtime();
    if (!now?.renderer) return;
    stage.setRenderer(now.renderer, { softwareRendering: now.softwareRendering === true });
    render();
  }, [stage, tick]);
  // The faces are drawn as the 2D view draws the board fitted to this pane (its hairlines a pixel, its
  // labels at that detail): fixed once the pane is known, so a resize redraws nothing. A pane with no size
  // yet is drawn at its first resize (the viewport's settle, `requestPaint`): its stage is presentable only
  // once a face is drawn.
  const lineScale = useRef(0);
  const lookKey = JSON.stringify([{ ...display, side: null }, colorScheme]);
  const applyLook = () => {
    const { width, height } = paneSize(), sheet = stage.sheet;
    if (!lineScale.current && width > 0 && height > 0) lineScale.current = Math.min(width / sheet.width, height / sheet.height) * 0.88;
    return lineScale.current > 0 && stage.setLook({ display: live.current.display, theme: live.current.colorScheme, lineScale: lineScale.current });
  };
  useEffect(() => {
    if (applyLook()) paintOverlay();
    render();
  }, [stage, lookKey, tick]);

  // ---- the camera ------------------------------------------------------------------------------
  const camera = () => runtime()?.camera || null;
  const paneSize = () => {
    const element = runtime()?.renderer?.domElement;
    return element ? { width: element.clientWidth, height: element.clientHeight } : { width: 0, height: 0 };
  };
  const sideNow = () => {
    const current = camera();
    if (!current) return live.current.display.side;
    const direction = new THREE.Vector3();
    current.getWorldDirection(direction);
    return sideSeenAlong(direction.toArray());
  };
  // Millimetres a CSS pixel spans at a world point (at the camera's target when none).
  const pixelSize = (point = null) => {
    const current = camera(), target = runtime()?.controls?.target;
    if (!current) return 0;
    const depth = new THREE.Vector3().copy(point || target || new THREE.Vector3()).sub(current.position)
      .dot(current.getWorldDirection(new THREE.Vector3()));
    return millimetresPerPixel(current.isOrthographicCamera
      ? { orthographic: true, halfHeight: (current.top - current.bottom) / 2 / (current.zoom || 1) }
      : { orthographic: false, fov: current.getEffectiveFOV() }, depth, paneSize().height);
  };
  // A pane point's ray, in world arrays.
  const rayAt = point => {
    const current = camera(), { width, height } = paneSize();
    if (!current || !(width > 0) || !(height > 0)) return null;
    current.updateMatrixWorld();
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(new THREE.Vector2((point.x / width) * 2 - 1, 1 - (point.y / height) * 2), current);
    return raycaster.ray;
  };

  // ---- the overlay: the board view's highlight and ink, on both faces --------------------------
  const paintFrame = useRef(0);
  const paintOverlay = () => {
    const scale = pixelSize();
    stage.setOverlay((ctx, frame) => live.current.overlay(ctx, frame), { lineScale: scale > 0 ? 1 / scale : 1 });
    const ink = live.current.bodyInk?.();
    if (ink) bodiesRef.current?.setInk(ink);
    render();
  };
  const requestPaint = () => {
    if (paintFrame.current) return;
    paintFrame.current = requestAnimationFrame(() => { paintFrame.current = 0; if (!lineScale.current) applyLook(); paintOverlay(); });
  };
  useEffect(() => () => cancelAnimationFrame(paintFrame.current), []);

  // ---- opening: head on, shown once it is the board's picture, then eased to where it goes ------
  const [initial] = useState(() => scopeShellCamera(opening.camera, modelKey, SCALE));
  const [presented, setPresented] = useState(false);
  const presentation = useCallback(state => setPresented(state.key === modelKey && !state.preparing), [modelKey]);
  const eased = useRef(false);
  const opened = useRef(null);
  // Head on in perspective, the eye stands where the face is drawn at the flat picture's scale for the lens
  // the viewport has (its focal length at its aspect), set before the first frame can be drawn (the faces
  // are drawn in this same pass); a lens or a projection changed later keeps that scale at the target.
  useEffect(() => {
    const now = runtime();
    if (eased.current || !opening.flat || !initial || !now?.camera?.isPerspectiveCamera) return;
    viewerRef.current?.setPerspective?.(perspectiveHeadOn(initial, now.camera.getEffectiveFOV()), { animate: false });
  }, [stage, tick]);
  // The viewport has drawn the board with its face (its stage `presentable`), head on: the board view
  // shows this canvas now, in place of the flat one, which shows the same picture.
  useEffect(() => { if (presented) live.current.onShown(); }, [presented]);
  // Shown and drawn, it eases from head on, to a camera on the side the 2D view showed (`cameraOnSide`): the
  // camera the file was left at in 3D, turned over to that side if it looks at the other, or Home's tilt from
  // that side, so the ease never crosses the board's plane. The hands on the camera then are the opening's own,
  // and any after them somebody's (`moved`).
  useEffect(() => {
    if (!shown || !presented || eased.current || !runtime()) return;
    eased.current = true;
    const viewer = viewerRef.current;
    const left = plainShellCamera(opening.then);
    const next = left ? scopeShellCamera(cameraOnSide(left, opening.side), modelKey, SCALE) : null;
    if (next) viewer?.setPerspective?.(next, { animate: true });
    else if (opening.home) {
      // Home's direction, as a camera on the origin, on that side.
      const home = cameraOnSide({ position: [...DEFAULT_VIEW_DIRECTION], target: [0, 0, 0], up: [...WORLD_UP] }, opening.side);
      viewer?.goHome?.({ direction: home.position, up: home.up });
    }
    opened.current = cameraHands(runtime());
  }, [shown, presented]);
  // The side the camera looks at is drawn on every stage: a revision is a new stage under a camera that
  // does not move, so no perspective change tells it the camera is under the board.
  useEffect(() => { if (stage.see(sideNow())) render(); }, [stage, tick]);
  const perspectiveChange = useCallback(snapshot => {
    const plain = plainShellCamera(snapshot);
    if (!plain) return;
    const side = sideSeenAlong(plain.target.map((value, axis) => value - plain.position[axis]));
    if (stage.see(side)) render();
    live.current.onCamera(plain, side);
  }, [stage]);

  // ---- what the board view reads of it --------------------------------------------------------
  useImperativeHandle(handle, () => ({
    canvas: () => runtime()?.renderer?.domElement || null,
    ray: point => { const ray = rayAt(point); return ray ? { origin: ray.origin.toArray(), direction: ray.direction.toArray() } : null; },
    project: world => {
      const current = camera(), { width, height } = paneSize();
      if (!current) return null;
      const point = new THREE.Vector3(...world);
      if (point.clone().sub(current.position).dot(current.getWorldDirection(new THREE.Vector3())) <= 0) return null;
      point.project(current);
      return { x: ((point.x + 1) / 2) * width, y: ((1 - point.y) / 2) * height };
    },
    side: sideNow,
    thickness: () => thickness,
    /** Where a pane point lands on the board: its sheet point, the side it meets, and how far a pick there reaches (`px` pixels). */
    atPoint(point, px) {
      const ray = rayAt(point);
      const located = ray ? stage.locate(ray) : null;
      if (!located) return null;
      const size = pixelSize(new THREE.Vector3(...located.point));
      return { page: located.page, side: located.side, reach: px * size };
    },
    /** The part whose body is under a pane point, in front of the face (`{ ref, distance }`), else null. */
    bodyAt(point) {
      const ray = rayAt(point);
      return ray ? bodyOn(ray) : null;
    },
    /** Measure's camera: from the sheet (its points' frame) to clip space, through the face the camera sees. */
    measureCamera() {
      const current = camera();
      if (!current) return null;
      current.updateMatrixWorld();
      const sheet = new THREE.Matrix4().fromArray(sheetToWorldMatrix(sideNow(), thickness));
      return { matrixWorldInverse: current.matrixWorldInverse.clone().multiply(sheet), projectionMatrix: current.projectionMatrix };
    },
    requestPaint,
    fit: () => viewerRef.current?.resetZoom?.(),
    /** A page box framed, the camera's direction kept. */
    frameSheet: ([x0, y0, x1, y1]) => viewerRef.current?.zoomToBounds?.({ min: [x0, -y1, -thickness], max: [x1, -y0, 0] }),
    /** The camera turned over to `side`, eased: Flip's (a move of the camera, as a hand's is: `moved`). */
    turnTo(side) {
      const viewer = viewerRef.current, now = viewer?.getPerspective?.();
      if (!now || sideNow() === side) return;
      viewer.setPerspective({ ...now, ...cameraTurnedOver(now) }, { animate: true });
    },
    /** Whether anybody has moved the camera since it was shown and eased to where it opens: leaving 3D then frames its `plan`. */
    moved: () => opened.current !== null && cameraHands(runtime()) !== opened.current,
    /** The 3D camera as the 2D view's window: what leaving 3D frames once the camera has moved, and what a prompt's view is. */
    plan(mirrorX) {
      const current = camera(), target = runtime()?.controls?.target, { width, height } = paneSize();
      if (!current || !target) return null;
      return planFromCamera({ position: current.position.toArray(), target: target.toArray(), halfHeight: (pixelSize(target) * height) / 2,
        perspective: Boolean(current.isPerspectiveCamera), width, height, mirrorX, thickness });
    },
    camera: () => plainShellCamera(viewerRef.current?.getPerspective?.()),
    setCamera: camera => viewerRef.current?.setPerspective?.(scopeShellCamera(camera, modelKey, SCALE), { animate: false }),
    capture: () => viewerRef.current.captureScreenshotBlob(),
    stats: () => ({ ...stage.stats(), parts: bodies.stats() })
  }), [stage, bodies, modelKey, thickness]);

  // ---- the viewport -------------------------------------------------------------------------------
  const children = useCallback(viewport => {
    viewportRef.current = viewport;
    return <>
      <ReadyTick tick={viewport.viewerReadyTick} onTick={setTick} />
      <PointerPick viewport={viewport} scene={POINTER_ONLY} enabled={picking} sameHit={() => false}
        onPick={(_hit, { multiSelect }, pointer) => live.current.onTap({ x: pointer.x, y: pointer.y }, { shiftKey: multiSelect, pointerType: "mouse" })}
        onHover={(_hit, pointer) => live.current.onHover(pointer ? { x: pointer.x, y: pointer.y } : null, pointer ? { pointerType: "mouse" } : null)} />
      <DoubleClickFit viewport={viewport} scene={stage} viewerRef={viewerRef} />
    </>;
  }, [stage, picking, viewerRef]);
  // Unseen until shown: see-through (the viewport's cover with it) and deaf to the pointer, over the flat canvas.
  return <div ref={frameRef} className={shown ? "absolute inset-0 z-0" : "pointer-events-none absolute inset-0 z-0 opacity-0"} data-board-3d="">
    <ShellViewport ref={viewerRef} scene={stage} modelKey={modelKey} sceneScaleMode={SCALE} perspective={initial} {...props}
      viewCube={false} onPerspectiveChange={perspectiveChange} onPresentationChange={presentation} onCameraSettled={requestPaint}>{children}</ShellViewport>
  </div>;
}

/** Tells its owner the viewport's runtime changed (a first one, a recovered context). */
function ReadyTick({ tick, onTick }) {
  useEffect(() => { onTick(tick); }, [tick, onTick]);
  return null;
}
