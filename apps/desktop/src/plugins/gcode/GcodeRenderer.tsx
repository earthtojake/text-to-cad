import { Route, Scan } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type { FileRendererProps } from "@hardcore/ui/file-viewer";
import { PromptContextAction } from "@hardcore/ui/host";
import { Button } from "@hardcore/ui/primitives/button";
import { cn } from "@hardcore/ui/utils";

import type { GcodeViewState } from "./live";
import { parseGcode, type GcodeToolpath } from "./parse";
import type { GcodeRendererData } from "./viewer";

/**
 * A sliced print's toolpath in 3D: the extrusion coloured by layer, cool at the bed and warm at
 * the top, with the travel moves on request. The slider shows the print up to a layer, which is
 * also what the agent sets with `set_gcode_layer` and sees with `capture_gcode`. Drag orbits,
 * right-drag pans, the wheel zooms; Fit frames the part again.
 */

const BED_COLOR = new THREE.Color("#2dd4bf");
const TOP_COLOR = new THREE.Color("#f97316");

function layerColors(toolpath: GcodeToolpath) {
  const colors = new Float32Array(toolpath.extrude.length);
  const last = Math.max(1, toolpath.layerZ.length - 1);
  const color = new THREE.Color();
  toolpath.extrudeLayer.forEach((layer, index) => {
    color.copy(BED_COLOR).lerpHSL(TOP_COLOR, layer / last);
    for (const offset of [0, 3]) colors.set([color.r, color.g, color.b], index * 6 + offset);
  });
  return colors;
}

interface Scene {
  renderer: THREE.WebGLRenderer;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  extrude: THREE.LineSegments;
  travel: THREE.LineSegments;
  render: () => void;
  fit: () => void;
}

export default function GcodeRenderer({ data, file, source, state, onStateChange, onReady }: FileRendererProps<GcodeRendererData>) {
  const toolpath = useMemo(() => parseGcode(data.text), [data.text]);
  const layers = toolpath.stats.layers;
  const saved = state && typeof state === "object" && !Array.isArray(state) ? state.layer : undefined;
  const [layer, updateLayer] = useState(typeof saved === "number" && saved >= 1 && saved <= layers ? saved : layers);
  const [showTravel, setShowTravel] = useState(false);
  const [feedback, setFeedback] = useState("");
  const pane = useRef<HTMLDivElement>(null);
  const scene = useRef<Scene | null>(null);
  // The live view reads these outside render; `setLayer` writes the ref first.
  const layerRef = useRef(layer);
  const changeRef = useRef(onStateChange);
  useEffect(() => { changeRef.current = onStateChange; }, [onStateChange]);
  const setLayer = useCallback((value: number) => {
    layerRef.current = value; updateLayer(value); changeRef.current({ layer: value });
  }, []);

  useEffect(() => {
    const host = pane.current;
    if (!host) return undefined;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.domElement.className = "absolute inset-0 size-full";
    host.appendChild(renderer.domElement);
    const world = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 10_000);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);

    const extrudeGeometry = new THREE.BufferGeometry();
    extrudeGeometry.setAttribute("position", new THREE.BufferAttribute(toolpath.extrude, 3));
    extrudeGeometry.setAttribute("color", new THREE.BufferAttribute(layerColors(toolpath), 3));
    const extrude = new THREE.LineSegments(extrudeGeometry, new THREE.LineBasicMaterial({ vertexColors: true }));
    const travelGeometry = new THREE.BufferGeometry();
    travelGeometry.setAttribute("position", new THREE.BufferAttribute(toolpath.travel, 3));
    const travel = new THREE.LineSegments(travelGeometry, new THREE.LineBasicMaterial({ color: "#94a3b8", transparent: true, opacity: 0.35 }));
    travel.visible = false;
    world.add(extrude, travel);

    const extents = toolpath.stats.extents;
    const box = extents ? new THREE.Box3(new THREE.Vector3(...extents.min), new THREE.Vector3(...extents.max)) : new THREE.Box3(new THREE.Vector3(-10, -10, 0), new THREE.Vector3(10, 10, 1));
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    // A bed grid under the part, in 10 mm squares.
    const span = Math.ceil((Math.max(size.x, size.y) * 1.6) / 10) * 10 || 20;
    const grid = new THREE.GridHelper(span, span / 10, "#64748b", "#334155");
    grid.rotation.x = Math.PI / 2;
    grid.position.set(center.x, center.y, box.min.z);
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.35;
    world.add(grid);

    const render = () => renderer.render(world, camera);
    const fit = () => {
      const radius = Math.max(1, box.getBoundingSphere(new THREE.Sphere()).radius);
      const distance = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.1;
      const direction = new THREE.Vector3(-0.9, -1.3, 1).normalize();
      camera.position.copy(center).addScaledVector(direction, distance);
      camera.near = distance / 100; camera.far = distance * 100; camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
      render();
    };
    const resize = () => {
      const width = Math.max(1, host.clientWidth), height = Math.max(1, host.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height; camera.updateProjectionMatrix();
      render();
    };
    controls.addEventListener("change", render);
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize(); fit();
    scene.current = { renderer, camera, controls, extrude, travel, render, fit };
    onReady(true);
    return () => {
      scene.current = null;
      observer.disconnect();
      controls.dispose();
      extrudeGeometry.dispose(); travelGeometry.dispose();
      (extrude.material as THREE.Material).dispose(); (travel.material as THREE.Material).dispose();
      grid.geometry.dispose(); (grid.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [toolpath, onReady]);

  useEffect(() => {
    const current = scene.current;
    if (!current) return;
    current.extrude.geometry.setDrawRange(0, (toolpath.layerEnd[layer - 1] ?? 0) * 2);
    // The last layer shows every travel move, the lift off the part and the park after it too.
    current.travel.geometry.setDrawRange(0, layer === layers ? Infinity : (toolpath.layerTravelEnd[layer - 1] ?? 0) * 2);
    current.travel.visible = showTravel;
    current.render();
  }, [toolpath, layer, layers, showTravel]);

  const viewState = useCallback((): GcodeViewState => ({
    ...toolpath.stats, path: file.path, revision: data.revision,
    layer: layerRef.current, layerZ: toolpath.layerZ[layerRef.current - 1] ?? null,
  }), [toolpath, file.path, data.revision]);
  const capture = useCallback(() => new Promise<Blob>((resolve, reject) => {
    const current = scene.current;
    if (!current) { reject(new Error("The toolpath is not showing.")); return; }
    current.render();
    current.renderer.domElement.toBlob(blob => blob ? resolve(blob) : reject(new Error("G-code capture failed.")), "image/png");
  }), []);

  useEffect(() => data.bind({
    path: file.path,
    state: viewState,
    setLayer(value) {
      if (!Number.isInteger(value) || value < 1 || value > layers) throw new Error(`Layer must be an integer between 1 and ${layers}.`);
      setLayer(value);
      return viewState();
    },
    capture,
  }), [data, file.path, layers, setLayer, viewState, capture]);

  const stats = toolpath.stats;
  const height = toolpath.layerZ[layer - 1];
  return (
    <div className="flex h-full min-h-0 flex-col bg-muted/30" aria-label={`G-code ${file.name}`}>
      <div className="flex h-9 shrink-0 items-center gap-2 border-b px-3 text-tiny text-muted-foreground">
        <label className="flex min-w-0 flex-1 items-center gap-2">
          <span className="shrink-0 tabular-nums">Layer {layer} of {layers}</span>
          <input aria-label="G-code layer" className="min-w-0 flex-1 accent-primary" disabled={layers < 2} max={Math.max(1, layers)} min={1}
            onChange={event => setLayer(Number(event.target.value))} type="range" value={layer} />
          <span className="w-16 shrink-0 tabular-nums">{height === undefined ? "" : `Z ${height.toFixed(2)}`}</span>
        </label>
        <Button aria-pressed={showTravel} className={cn("h-6 gap-1.5 px-2 text-tiny font-normal", showTravel && "bg-muted")} onClick={() => setShowTravel(value => !value)} size="sm" variant="ghost">
          <Route className="size-3" />Travel
        </Button>
        <Button className="h-6 gap-1.5 px-2 text-tiny font-normal" onClick={() => scene.current?.fit()} size="sm" variant="ghost">
          <Scan className="size-3" />Fit
        </Button>
        <PromptContextAction className="h-6 px-2 text-tiny font-normal" size="sm" variant="ghost" disabled={layers === 0} createContext={() => ({
          schemaVersion: 1, operationId: crypto.randomUUID(), parts: [
            { id: "gcode", kind: "reference", reference: { resource: { kind: "workspace-file", workspaceId: source.id, path: file.path, revision: data.revision }, target: { kind: "whole-resource" }, label: `${file.name}, layers 1–${layerRef.current} of ${layers}` } },
            { id: "toolpath", kind: "attachment", name: `${file.name}-layer-${layerRef.current}.png`, mimeType: "image/png", content: capture(), about: ["gcode"] },
          ] })}
          onResult={result => setFeedback(result.status === "added" || result.status === "copied" || result.status === "cancelled" ? "" : ("message" in result ? result.message : undefined) ?? result.status)} />
        <span role="status">{feedback}</span>
      </div>
      <div ref={pane} className="relative min-h-0 flex-1 cursor-grab touch-none overflow-hidden active:cursor-grabbing" data-gcode-view="">
        {layers === 0 ? <div className="absolute inset-0 flex items-center justify-center text-ui text-muted-foreground">No extruding moves in this file.</div> : null}
      </div>
      <div className="flex h-8 shrink-0 items-center gap-3 overflow-hidden whitespace-nowrap border-t px-3 text-tiny text-muted-foreground tabular-nums">
        <span>{stats.extrudeMoves.toLocaleString()} extrude · {stats.travelMoves.toLocaleString()} travel{stats.arcMoves ? ` · ${stats.arcMoves.toLocaleString()} ${stats.arcMoves === 1 ? "arc" : "arcs"}` : ""}</span>
        <span>{(stats.filamentMm / 1000).toFixed(2)} m filament</span>
        {stats.extents ? <span>{(["X", "Y", "Z"] as const).map((axis, index) => `${axis} ${(stats.extents!.max[index]! - stats.extents!.min[index]!).toFixed(1)}`).join(" × ")} mm</span> : null}
      </div>
    </div>
  );
}
