// React face of viewport LOD (design/unified-tessellation.md Phase 5).
//
// Owns a lodScheduler for the current package: camera-settle events sample
// the viewer (projection, viewport height, live distances to each unique
// component's nearest occurrence), the scheduler picks the worst offender,
// the level-keyed loader re-tessellates it in the surf worker pool, and the
// payload swaps in through useCadAssets' re-composition. Kill switch for
// debugging: `window.__CAD_VIEWER_LOD__ = false` before loading a model.
import { useCallback, useEffect, useRef } from "react";

import { loadRenderSurfPayloadAtLevel } from "cadgen-js/lib/renderAssetClient";
import { LOD_CHORD_LEVELS } from "cadgen-js/lib/surf/lodPolicy.js";

import { createLodScheduler } from "./lodScheduler.js";

function lodEnabled() {
  return typeof window === "undefined" || window.__CAD_VIEWER_LOD__ !== false;
}

export function useViewportLod({ viewerRef, lodPackage, applyComponentLodPayload }) {
  const componentsRef = useRef(new Map());
  const applyRef = useRef(applyComponentLodPayload);
  applyRef.current = applyComponentLodPayload;
  const schedulerRef = useRef(null);

  useEffect(() => {
    const scheduler = createLodScheduler({
      loadLevel: (cid, level, { signal }) => {
        const component = componentsRef.current.get(cid);
        if (!component) {
          return Promise.reject(new Error(`unknown LOD component ${cid}`));
        }
        return loadRenderSurfPayloadAtLevel(component.surfUrl, {
          signal,
          // Level 0 is the plain-URL cache entry the initial load shares.
          tessellation: level > 0 ? { chordTolerance: LOD_CHORD_LEVELS[level] } : undefined
        });
      },
      applyLevel: (cid, level, payload) => {
        applyRef.current?.(cid, level, payload);
        // Observable swap signal: headless verification and debugging listen
        // for it; carries no payload references.
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("cad:lod-level", { detail: { cid, level } }));
        }
      }
    });
    schedulerRef.current = scheduler;
    return () => {
      scheduler.dispose();
      schedulerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const components = lodEnabled() ? lodPackage?.components || [] : [];
    componentsRef.current = new Map(components.map((component) => [component.cid, component]));
    schedulerRef.current?.setComponents(
      components.map(({ cid, diagonal }) => ({ cid, diagonal }))
    );
  }, [lodPackage]);

  // Call on every camera change (perspective callback); the scheduler owns the
  // debounce, so this must stay cheap.
  const onCameraMoved = useCallback(() => {
    if (!componentsRef.current.size) {
      return;
    }
    const sampler = viewerRef.current?.sampleLodCamera?.();
    if (!sampler) {
      return;
    }
    schedulerRef.current?.onCameraSample({
      camera: sampler.camera,
      viewportHeightPx: sampler.viewportHeightPx,
      distanceFor: (cid) => {
        const component = componentsRef.current.get(cid);
        if (!component?.centers?.length) {
          return NaN;
        }
        let best = Infinity;
        for (const center of component.centers) {
          const distance = sampler.distanceToModelPoint(center[0], center[1], center[2]);
          if (distance < best) {
            best = distance;
          }
        }
        return best;
      }
    });
  }, [viewerRef]);

  return { onCameraMoved };
}
