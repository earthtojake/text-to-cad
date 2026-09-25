import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { useViewportCamera } from './useViewportCamera.js';
import { readRuntimeZoomPercent, stepCameraTransition } from './runtimeCamera.js';
import { VIEW_PLANE_FACE_BY_ID, viewPlaneCameraBasis, WORLD_UP } from './viewportCameraKit.js';

afterEach(cleanup);
const ref = (current: any = null) => ({ current });

for (const orthographic of [true, false]) {
  it(`preserves zoom and target for every cube face, edge and corner in ${orthographic ? 'orthographic' : 'perspective'}`, () => {
    const runtimeRef = ref();
    const original = { min: [-20, -10, -5], max: [20, 10, 5] };
    const { result } = renderHook(() => useViewportCamera({
      runtimeRef, modelBounds: original, modelKey: 'fixture', modelKeyRef: ref('fixture'),
      coordinateSystemFor: () => 'cad-z-up-v1', activeViewPlaneFaceRef: ref(''), defaultPerspectiveResettingRef: ref(false),
      fullscreenCameraRef: ref(), lastEmittedPerspectiveRef: ref(), cameraMovedRef: ref(),
      modelTransformRef: ref({ offset: [0, 0, 0] }), perspectiveChangeRef: ref(), perspectivePropRef: ref(),
      perspectiveRef: ref(), previewMode: false, previewModeRef: ref(false), previewOrbitSpeed: 0,
      runWithoutPerspectiveEvents: (callback: () => unknown) => callback(), sceneScaleModeRef: ref('cad'),
      setActiveViewPlaneFace: vi.fn(), setDefaultPerspectiveDetached: vi.fn(), setViewPlaneOrientation: vi.fn(),
      suppressPerspectiveEventsRef: ref(0), viewerReadyTick: 0
    }));
    const camera = orthographic ? new THREE.OrthographicCamera(-50, 50, 40, -40, 0.01, 10000)
      : new THREE.PerspectiveCamera(48, 1.25, 0.01, 10000);
    camera.up.set(0, 0, 1);
    camera.userData.cadHalfHeight = 40;
    const runtime = { THREE, camera, orthographicCamera: orthographic ? camera : null, perspectiveCamera: orthographic ? null : camera, controls: { target: new THREE.Vector3(), update() {} },
      zeroPoseBounds: original, modelBounds: { min: [-500, -500, -500], max: [500, 500, 500] },
      renderer: { domElement: { clientWidth: 1000, clientHeight: 800 } }, width: 1000, height: 800 } as any;
    runtimeRef.current = runtime;
    for (const preset of Object.values(VIEW_PLANE_FACE_BY_ID) as any[]) {
      camera.position.set(2000, -3000, 700);
      camera.zoom = 8;
      runtime.controls.target.set(400, 100, 80);
      act(() => { expect(result.current.activateViewPlaneFace(preset.id)).toBe(true); });
      stepCameraTransition(runtime, runtime.cameraTransition.startTime + 1000);
      expect(runtime.controls.target.toArray()).toEqual([400, 100, 80]);
      expect(camera.zoom).toBe(8);
      expect(camera.position.distanceTo(runtime.controls.target)).toBeCloseTo(Math.hypot(1600, -3100, 620), 6);
      const direction = camera.position.clone().sub(runtime.controls.target).normalize();
      const expected = new THREE.Vector3(...viewPlaneCameraBasis(preset, WORLD_UP).direction);
      expect(direction.dot(expected)).toBeCloseTo(1, 8);
    }
    act(() => { expect(result.current.activateDefaultViewPlane()).toBe(true); });
    stepCameraTransition(runtime, runtime.cameraTransition.startTime + 1000);
    expect(runtime.controls.target.toArray()).toEqual([0, 0, 0]);
    expect(camera.zoom).toBe(1);
    expect(readRuntimeZoomPercent(runtime)).toBeCloseTo(100, 5);
    expect(runtime.interactiveFraming.bounds).toEqual(original);
  });
}
