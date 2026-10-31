import { useEffect } from "react";
import * as THREE from "three";
import { createSceneClip } from "@text-to-cad/core/lib/viewer/sceneClip.js";

/**
 * Clip and Explode on a scene the viewport holds, as the view says them (`displaySettings`'s
 * `clip` and `exploded`), for a scene that leaves them to the viewport (`enabled`): after its look,
 * which dresses the materials a cut is drawn on. Explode moves its parts through the scene's own
 * `setExplode` (the stage follows the box they make: `onBoundsChanged`); Clip's plane, placed in the
 * box the camera frames, cuts what the look dressed and caps it (`sceneClip.js`). The planes in force
 * are the runtime's (`activeClipPlanes`), which the ink and the measurements are cut by too.
 *
 * @param {{ runtimeRef: { current: object | null }, scene: object | null, displaySettings: object | null,
 *   enabled: boolean, look: unknown, loading: boolean, viewerReadyTick: number, onBoundsChanged: () => void }} options
 *   `look`: the look the scene wears, so a new one is cut again.
 */
export function useSceneEffects({ runtimeRef, scene, displaySettings, enabled, look, loading, viewerReadyTick, onBoundsChanged }) {
  const exploded = displaySettings?.exploded;
  const amount = enabled && exploded?.enabled ? Number(exploded.amount) || 0 : 0;
  const clip = enabled ? displaySettings?.clip ?? null : null;
  const clipKey = JSON.stringify(clip);
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime || !enabled) return;
    if (scene?.setExplode?.(amount)) onBoundsChanged();
    runtime.sceneClip ??= createSceneClip(THREE, { stage: runtime.scene });
    runtime.activeClipPlanes = runtime.sceneClip.sync(loading ? null : scene, clip);
    runtime.requestRender();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene, look, clipKey, amount, enabled, loading, viewerReadyTick]);
  useEffect(() => {
    const runtime = runtimeRef.current;
    return () => { runtime?.sceneClip?.dispose(); if (runtime) { runtime.sceneClip = null; runtime.activeClipPlanes = []; } };
  }, [runtimeRef, viewerReadyTick]);
}
