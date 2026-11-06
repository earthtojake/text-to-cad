/**
 * A board in 3D: the 3D views' own viewport (`kit/shell/ShellViewport.jsx`: its camera, its gestures,
 * its cube, its keys) around the bare board (`@cad/core/lib/board3d/boardStage.js`: a slab cut to the
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
 * sits on its canvas as it does in 2D. It opens on `opening.camera` (the 2D window head on, or the
 * camera it was left at) and then eases to `opening.then` (the camera this file was left at in 3D) or
 * to Home.
 */
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { boardPalette } from "@cad/core/lib/plot2d/index.js";
import { createBoardStage } from "@cad/core/lib/board3d/boardStage.js";
import { BOARD_THICKNESS_MM, cameraTurnedOver, millimetresPerPixel, planFromCamera, sheetToWorldMatrix, sideSeenAlong } from "@cad/core/lib/board3d/boardFrame.js";
import { VIEWER_SCENE_SCALE } from "@cad/core/lib/viewer/sceneScale.js";
import ShellViewport from "../kit/shell/ShellViewport.jsx";
import DoubleClickFit from "../kit/shell/DoubleClickFit.jsx";
import { useStageViewport } from "../kit/shell/useStageViewport.js";
import { plainShellCamera, scopeShellCamera } from "../kit/shell/fileView.js";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";

const SCALE = VIEWER_SCENE_SCALE.CAD;

/**
 * @param {{ handle: { current: object | null }, viewerRef: { current: object | null }, modelKey: string,
 *   layout: object, outline: number[][][] | null, display: object, colorScheme: "light" | "dark",
 *   opening: { camera: object, then: object | null }, projection: string,
 *   pickAt(located: object): object | null, onTap(point: object, event: object): void, onHover(point: object | null, event: object | null): void,
 *   picking: boolean, selecting: boolean, overlay(ctx: CanvasRenderingContext2D, frame: object): boolean,
 *   onCamera(camera: object, side: "top" | "bottom"): void, onShown(): void }} props
 */
export default function Board3dView({ handle, viewerRef, modelKey, layout, outline, display, colorScheme, opening, projection, pickAt, onTap, onHover,
  picking, selecting, overlay, onCamera, onShown }) {
  const thickness = BOARD_THICKNESS_MM;
  const live = useRef(null);
  live.current = { pickAt, onTap, onHover, overlay, onCamera, onShown, display, colorScheme };
  // The viewport the 3D views' overlay is handed: its runtime, and the element its pointer events arrive on.
  const viewportRef = useRef(null);
  const stage = useMemo(() => createBoardStage(THREE, { layout, outline, thickness, theme: colorScheme,
    pickAt: located => live.current.pickAt(located) }), [layout, outline]);
  useEffect(() => () => stage.dispose(), [stage]);
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
  const render = () => {
    const { drawnSides, texturePixels, faceMs } = stage.stats();
    const element = frameRef.current;
    if (element) Object.assign(element.dataset, { boardFaces: drawnSides.join(" "), boardTextureMp: (texturePixels / 1e6).toFixed(1), boardFaceMs: faceMs.toFixed(0) });
    runtime()?.requestRender?.();
  };
  useEffect(() => {
    const now = runtime();
    if (!now?.renderer) return;
    stage.setRenderer(now.renderer, { softwareRendering: now.softwareRendering === true });
    render();
  }, [stage, tick]);
  // The faces are drawn as the 2D view draws the board fitted to this pane (its hairlines a pixel, its
  // labels at that detail): fixed once the pane is known, so a resize redraws nothing.
  const lineScale = useRef(0);
  const lookKey = JSON.stringify([{ ...display, side: null }, colorScheme]);
  useEffect(() => {
    const { width, height } = paneSize(), sheet = stage.sheet;
    if (!lineScale.current && width > 0 && height > 0) lineScale.current = Math.min(width / sheet.width, height / sheet.height) * 0.88;
    if (!lineScale.current) return;
    if (stage.setLook({ display, theme: colorScheme, lineScale: lineScale.current })) paintOverlay();
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
    render();
  };
  const requestPaint = () => {
    if (paintFrame.current) return;
    paintFrame.current = requestAnimationFrame(() => { paintFrame.current = 0; paintOverlay(); });
  };
  useEffect(() => () => cancelAnimationFrame(paintFrame.current), []);

  // ---- opening: head on, then eased to where it goes ------------------------------------------
  const [initial] = useState(() => scopeShellCamera(opening.camera, modelKey, SCALE));
  const eased = useRef(false);
  const [presented, setPresented] = useState(false);
  const presentation = useCallback(state => setPresented(state.key === modelKey && !state.preparing), [modelKey]);
  useEffect(() => {
    if (!presented || eased.current || !runtime()) return;
    eased.current = true;
    live.current.onShown();
    const viewer = viewerRef.current;
    const next = opening.then ? scopeShellCamera(opening.then, modelKey, SCALE) : null;
    if (next) viewer?.setPerspective?.(next, { animate: true });
    else if (opening.home) viewer?.goHome?.();
  }, [presented]);
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
    home: () => viewerRef.current?.goHome?.(),
    /** A page box framed, the camera's direction kept. */
    frameSheet: ([x0, y0, x1, y1]) => viewerRef.current?.zoomToBounds?.({ min: [x0, -y1, -thickness], max: [x1, -y0, 0] }),
    /** The camera turned to `side`, eased: Front | Back. */
    turnTo(side) {
      const viewer = viewerRef.current, now = viewer?.getPerspective?.();
      if (!now || sideNow() === side) return;
      viewer.setPerspective({ ...now, ...cameraTurnedOver(now) }, { animate: true });
    },
    /** The 3D camera as the 2D view's window: what leaving 3D frames, and what a prompt's view is. */
    plan(mirrorX) {
      const current = camera(), target = runtime()?.controls?.target, { width, height } = paneSize();
      if (!current || !target) return null;
      return planFromCamera({ position: current.position.toArray(), target: target.toArray(), halfHeight: (pixelSize(target) * height) / 2,
        width, height, mirrorX, thickness });
    },
    camera: () => plainShellCamera(viewerRef.current?.getPerspective?.()),
    setCamera: camera => viewerRef.current?.setPerspective?.(scopeShellCamera(camera, modelKey, SCALE), { animate: false }),
    capture: () => viewerRef.current.captureScreenshotBlob(),
    stats: () => stage.stats()
  }), [stage, modelKey]);

  // ---- the viewport -------------------------------------------------------------------------------
  const children = useCallback(viewport => {
    viewportRef.current = viewport;
    return <>
      <ReadyTick tick={viewport.viewerReadyTick} onTick={setTick} />
      <PointerPick viewport={viewport} scene={stage} enabled={picking} sameHit={() => false}
        onPick={(_hit, { multiSelect }, pointer) => live.current.onTap({ x: pointer.x, y: pointer.y }, { shiftKey: multiSelect, pointerType: "mouse" })}
        onHover={(_hit, pointer) => live.current.onHover(pointer ? { x: pointer.x, y: pointer.y } : null, pointer ? { pointerType: "mouse" } : null)} />
      <DoubleClickFit viewport={viewport} scene={stage} active={selecting} viewerRef={viewerRef} />
    </>;
  }, [stage, picking, selecting, viewerRef]);
  return <div ref={frameRef} className="absolute inset-0 z-0" data-board-3d="">
    <ShellViewport ref={viewerRef} scene={stage} modelKey={modelKey} sceneScaleMode={SCALE} perspective={initial} {...props}
      viewCube onPerspectiveChange={perspectiveChange} onPresentationChange={presentation} onCameraSettled={requestPaint}>{children}</ShellViewport>
  </div>;
}

/** Tells its owner the viewport's runtime changed (a first one, a recovered context). */
function ReadyTick({ tick, onTick }) {
  useEffect(() => { onTick(tick); }, [tick, onTick]);
  return null;
}
