"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createStage, palettes } from "@/lib/icon/stage.mjs";
import styles from "./icon-playground.module.css";

type Palette = keyof typeof palettes;
type Stage = Awaited<ReturnType<typeof createStage>>;

export function IconPlayground() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const stage = useRef<Stage | null>(null);
  const playback = useRef({ playing: false, speed: 4 });
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);
  const [palette, setPalette] = useState<Palette>("blue");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let cleanup = () => {};
    const surface = canvas.current!;
    const container = viewport.current!;
    createStage(surface).then(instance => {
      if (cancelled) { instance.dispose(); return; }
      stage.current = instance;
      instance.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
      const orbit = new OrbitControls(instance.camera, surface);
      orbit.enableDamping = true;
      orbit.enablePan = false;
      orbit.minDistance = 7;
      orbit.maxDistance = 16;
      const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
      playback.current.playing = !reducedMotion.matches;
      setPlaying(playback.current.playing);
      const onMotionChange = (event: MediaQueryListEvent) => {
        if (!event.matches) return;
        playback.current.playing = false;
        setPlaying(false);
        instance.renderAt(0);
      };
      reducedMotion.addEventListener("change", onMotionChange);
      const resize = () => {
        const { width, height } = container.getBoundingClientRect();
        if (!width || !height) return;
        instance.renderer.setSize(width, height, false);
        instance.camera.aspect = width / height;
        instance.camera.fov = width < height ? 40 / Math.max(width / height, 0.55) : 40;
        instance.camera.updateProjectionMatrix();
      };
      const observer = new ResizeObserver(resize);
      observer.observe(container);
      resize();
      let previous = performance.now();
      instance.renderer.setAnimationLoop(now => {
        const delta = Math.min((now - previous) / 1000, 0.05);
        previous = now;
        if (playback.current.playing && !document.hidden) {
          instance.mixer.update(delta * playback.current.speed);
        }
        orbit.update(delta);
        instance.renderer.render(instance.scene, instance.camera);
      });
      setReady(true);
      cleanup = () => {
        observer.disconnect();
        reducedMotion.removeEventListener("change", onMotionChange);
        orbit.dispose();
        instance.dispose();
        stage.current = null;
      };
    }).catch(cause => {
      if (!cancelled) setError(`Unable to load the icon: ${cause.message}`);
    });
    return () => { cancelled = true; cleanup(); };
  }, []);

  async function downloadPNG() {
    setExporting(true);
    setError("");
    let capture: Stage | undefined;
    try {
      // Always export the blue, fully expanded reference pose independently
      // of the preview's current playback, palette and camera position.
      capture = await createStage(document.createElement("canvas"));
      capture.renderer.setPixelRatio(1);
      capture.renderer.setSize(512, 512, false);
      capture.renderAt(0);
      const blob = await new Promise<Blob>((resolve, reject) => {
        capture!.renderer.domElement.toBlob(value => value ? resolve(value) : reject(new Error("PNG export failed")), "image/png");
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "icon-blue.png";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "PNG export failed");
    } finally {
      capture?.dispose();
      setExporting(false);
    }
  }

  return (
    <section aria-label="Loading animation playground" className={styles.playground} style={{ background: palettes[palette].background }}>
      <h2 className="sr-only">Animated loading icon</h2>
      <div ref={viewport} className={styles.viewport}>
        <canvas ref={canvas} aria-label="3D spiral icon. Drag to rotate and scroll to zoom." />
      </div>
      <div className={styles.downloads}>
        <Link href="/">Docs</Link>
        <button onClick={downloadPNG} disabled={!ready || exporting}>{exporting ? "Rendering…" : "Blue PNG"}</button>
        <a href="/icon/icon.glb" download>GLB</a>
      </div>
      {!ready && !error && <p className={styles.message} role="status">Loading icon…</p>}
      {error && <p className={styles.message} role="alert">{error}</p>}
      <div className={styles.controls}>
        <button disabled={!ready} aria-pressed={playing} onClick={() => {
          playback.current.playing = !playback.current.playing;
          setPlaying(playback.current.playing);
        }}>{playing ? "Pause" : "Play"}</button>
        <label className={styles.speed}>
          Speed <output>{speed}×</output>
          <input type="range" min="0.25" max="8" step="0.25" value={speed} disabled={!ready}
            aria-label="Animation speed" aria-valuetext={`${speed} times`} onChange={event => {
              const value = Number(event.target.value);
              playback.current.speed = value;
              setSpeed(value);
            }} />
        </label>
        <label className={styles.palette}>
          Palette
          <select value={palette} disabled={!ready} onChange={event => {
            const value = event.target.value as Palette;
            stage.current?.setPalette(value);
            setPalette(value);
          }}>
            {(["blue", "silver", "graphite", "gold", "violet"] as const).map(name =>
              <option key={name} value={name}>{name[0].toUpperCase() + name.slice(1)}</option>)}
          </select>
        </label>
      </div>
    </section>
  );
}
