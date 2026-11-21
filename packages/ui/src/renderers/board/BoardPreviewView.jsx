/**
 * A board's Preview: Preview's own view (`kit/shell/PreviewView.jsx`: its own viewport, camera and Render) around
 * the board as it is made, lit: core's stage in its `lit` form (`@cad/core/lib/board3d/boardStage.js`: the slab cut
 * to the outline, its two faces the 2D drawer's pictures of the two sides as lit surfaces, casting and taking
 * shadows, and none of the working view's layers) and the parts' bodies on it (`boardParts.js`, casting shadows, no
 * block for a missing model). A lazy chunk of the board's view (`BoardRenderer.jsx`), loaded as Preview is first
 * entered: a board that is never previewed loads no viewport for it.
 *
 * It is a view of its own, as every Preview is: built as Preview opens, from the board's plot and its models table,
 * and thrown away as it closes. Nothing of the working view reaches it (its 2D window, its 3D camera, its Display,
 * what is picked, isolated, measured or drawn), and it changes nothing of it. It draws the WHOLE board, the Display
 * every board opens with (`BOARD_DISPLAY_DEFAULTS`: Board, poured, every layer), in the viewport's theme, in its
 * stack-up's colours where its file names them; the Layers tab's 3D models eye alone carries over (off: no bodies).
 *
 * The faces are uploaded through Preview's viewport's renderer (`view.overlay`, handed the viewport), and the
 * stage is `presentable` only once both are drawn, so Preview's first frame is the board, never the bare slab.
 * The bodies arrive after it (each model read through the engine, four at a time): the scene says it is not
 * `complete` until they are in, its box growing as they land, so Preview's cover waits for them (`view.onComplete`,
 * the frame's `complete`) and the viewport frames the board once more when they are.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { createBoardStage } from "@cad/core/lib/board3d/boardStage.js";
import { createBoardParts, createModelLoader } from "@cad/core/lib/board3d/boardParts.js";
import { BOARD_DISPLAY_DEFAULTS } from "@cad/core/lib/plot2d/index.js";
import PreviewView from "../kit/shell/PreviewView.jsx";

const NO_PARTS = Object.freeze([]);

/**
 * @param {{ view: { layout: object, outline: number[][][] | null, thickness: number, parts: object[] | null, models: object | null,
 *   client: object | null, showModels: boolean, colorScheme: "light" | "dark", onComplete(complete: boolean): void },
 *   desired: object, modelKey: string, sceneScaleMode: string, viewRef: { current: object | null }, orbit?: boolean,
 *   orbitSpeed?: number, onPresented?: (presented: boolean) => void }} props  `PreviewView`'s, its `view` the board's.
 */
export default function BoardPreviewView({ view, ...preview }) {
  const { layout, outline, thickness, parts, models, client, showModels, colorScheme, onComplete } = view;
  const live = useRef(null);
  live.current = { client, colorScheme, onComplete };
  const stage = useMemo(() => createBoardStage(THREE, { layout, outline, thickness, theme: live.current.colorScheme, lit: true }), [layout, outline, thickness]);
  useEffect(() => () => stage.dispose(), [stage]);
  const bodies = useMemo(() => createBoardParts(THREE, { thickness, theme: live.current.colorScheme, shadows: true, blocks: false }), [thickness]);
  useEffect(() => () => bodies.dispose(), [bodies]);
  useEffect(() => {
    stage.object3D.add(bodies.object3D);
    return () => { stage.object3D.remove(bodies.object3D); };
  }, [stage, bodies]);

  // Preview's scene (`lib/viewer/sceneContract.js`): the stage, in the box of the slab with the bodies on it as they
  // stand now, not complete while more are on their way.
  const scene = useMemo(() => {
    const now = { bounds: stage.bounds, complete: false, shadowed: false };
    // Every surface takes shadows, the bodies that land later too.
    const shadow = () => stage.object3D.traverse(object => { if (object.isMesh) object.receiveShadow = now.shadowed; });
    return {
      object3D: stage.object3D,
      get bounds() { return now.bounds; },
      get restBounds() { return now.bounds; },
      get complete() { return now.complete; },
      presentable: () => stage.presentable(),
      setShadowReception(receives) { now.shadowed = receives === true; shadow(); },
      arrived(complete) { now.bounds = stage.shownBounds(); now.complete = complete; shadow(); },
      // The stage and the bodies are this view's, disposed with it.
      dispose() {}
    };
  }, [stage]);

  // The viewport Preview's view hands its overlay (`viewport`), and a tick as its runtime is made or replaced.
  const viewportRef = useRef(null);
  const [tick, setTick] = useState(0);
  const runtime = () => viewportRef.current?.runtimeRef.current || null;
  // What arrived (the parts placed, a model baked): the scene's box and whether it is whole, adopted by the viewport
  // in place and said to the frame, once a frame however many landed in it.
  const arrival = useRef(0);
  const arrive = useCallback(() => {
    if (arrival.current) return;
    arrival.current = requestAnimationFrame(() => {
      arrival.current = 0;
      const complete = bodies.wanted().length === 0;
      scene.arrived(complete);
      viewportRef.current?.commitScene?.();
      runtime()?.requestRender?.();
      live.current.onComplete(complete);
    });
  }, [bodies, scene]);
  useEffect(() => () => cancelAnimationFrame(arrival.current), []);

  const loader = useMemo(() => createModelLoader(THREE, {
    open: (document, options) => live.current.client.engineDocument(document, options),
    onModel: (key, baked) => { bodies.addModel(key, baked); arrive(); },
    onFailed: (key, reason) => { bodies.failModel(key, reason); arrive(); }
  }), [bodies, arrive]);
  useEffect(() => () => loader.dispose(), [loader]);
  // The parts as they stand: placed again where they changed, their models asked for. With 3D models off, none.
  // Before the first paint: the frame hears the bodies are still on their way before Preview's view presents.
  useLayoutEffect(() => {
    const readable = typeof live.current.client?.engineDocument === "function";
    bodies.setParts(showModels && readable ? parts || NO_PARTS : NO_PARTS, models);
    const wanted = bodies.wanted();
    if (wanted.length) loader.request(wanted);
    const complete = wanted.length === 0;
    scene.arrived(complete);
    live.current.onComplete(complete);
    arrive();
  }, [bodies, loader, scene, arrive, parts, models, showModels]);

  // ---- the faces: the whole board drawn, once Preview's renderer can take it ----------------------
  // Drawn as the 2D view draws the board fitted to this pane (its hairlines a pixel, its labels at that detail):
  // fixed once the pane is known. A pane with no size yet is drawn as its viewport settles (`onCameraSettled`).
  const lineScale = useRef(0);
  const applyLook = useCallback(() => {
    const now = runtime();
    if (!now?.renderer) return false;
    stage.setRenderer(now.renderer, { softwareRendering: now.softwareRendering === true });
    const element = now.renderer.domElement, sheet = stage.sheet;
    if (!lineScale.current && element.clientWidth > 0 && element.clientHeight > 0) {
      lineScale.current = Math.min(element.clientWidth / sheet.width, element.clientHeight / sheet.height) * 0.88;
    }
    if (!(lineScale.current > 0)) return false;
    const drew = stage.setLook({ display: BOARD_DISPLAY_DEFAULTS, theme: live.current.colorScheme, lineScale: lineScale.current });
    if (drew) now.requestRender?.();
    return drew;
  }, [stage]);
  useEffect(() => { bodies.setTheme(colorScheme); applyLook(); }, [bodies, applyLook, colorScheme, tick]);

  const overlay = useCallback(viewport => {
    viewportRef.current = viewport;
    return <ReadyTick tick={viewport.viewerReadyTick} onTick={setTick} />;
  }, []);
  const drawn = useMemo(() => ({ scene, overlay, onCameraSettled: () => { if (!lineScale.current) applyLook(); } }), [scene, overlay, applyLook]);
  return <PreviewView view={drawn} {...preview} />;
}

/** Tells its owner the viewport's runtime changed (a first one, a recovered context). */
function ReadyTick({ tick, onTick }) {
  useEffect(() => { onTick(tick); }, [tick, onTick]);
  return null;
}
