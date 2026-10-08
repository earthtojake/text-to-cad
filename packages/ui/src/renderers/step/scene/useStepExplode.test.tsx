import { cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { buildModel } from '@text-to-cad/core/common/cadScene.js';
import { useStepExplode } from './useStepExplode.js';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

// Two flat parts side by side, as the STEP scene's records.
function twoParts() {
  return {
    vertices: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 0, 3, 0, 0, 2, 1, 0]),
    indices: new Uint32Array([0, 1, 2, 3, 4, 5]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]),
    bounds: { min: [0, 0, 0], max: [3, 1, 0] },
    parts: [
      { id: 'left', vertexOffset: 0, vertexCount: 3, triangleOffset: 0, triangleCount: 1, bounds: { min: [0, 0, 0], max: [1, 1, 0] } },
      { id: 'right', vertexOffset: 3, vertexCount: 3, triangleOffset: 1, triangleCount: 1, bounds: { min: [2, 0, 0], max: [3, 1, 0] } }
    ]
  };
}

// The two parts as a viewer holds them, and the layers the explode layer reads: the view at `amount`,
// on or off (`active`), after the scene sync has made its records `token` times.
function twoPartView() {
  const meshData = twoParts();
  const cadScene = buildModel(THREE, meshData, { renderPartsIndividually: true });
  const rest = structuredClone(cadScene.restBounds);
  const runtime = { THREE, cadScene, displayRecords: cadScene.displayRecords, zeroPoseBounds: rest, requestRender() {} };
  const syncSceneBounds = vi.fn();
  const explosionRef = { current: { progress: 0, modelKey: '', enabled: false, layout: null } };
  const layers = ({ amount, active = true, token = 1 }: { amount: number, active?: boolean, token?: number }) => ({
    viewport: { runtimeRef: { current: runtime }, viewerReadyTick: 1, syncSceneBounds },
    props: { meshData, modelKey: 'two-parts', isLoading: false },
    policy: {
      explodedViewActive: active, explodeAmount: amount, normalizedExplodedSettings: { enabled: active, amount },
      focusedPartIds: [], normalizedThemeSettings: {}
    },
    displayRecordsToken: token,
    setExplodedViewPoseTick: vi.fn(),
    explosionRef
  });
  return { cadScene, rest, syncSceneBounds, explosionRef, layers };
}

// Where the parts are drawn: each record's rest box moved by its explosion.
function drawnBox(cadScene: ReturnType<typeof buildModel>) {
  const drawn = { min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity] };
  for (const record of cadScene.displayRecords) {
    const offset = record.explodedViewMatrix?.elements.slice(12, 15) || [0, 0, 0];
    for (let axis = 0; axis < 3; axis += 1) {
      drawn.min[axis] = Math.min(drawn.min[axis], record.partBounds.min[axis] + offset[axis]);
      drawn.max[axis] = Math.max(drawn.max[axis], record.partBounds.max[axis] + offset[axis]);
    }
  }
  return drawn;
}

function expectBoundedWhereDrawn(cadScene: ReturnType<typeof buildModel>) {
  const drawn = drawnBox(cadScene);
  for (const side of ['min', 'max'] as const) {
    cadScene.bounds[side].forEach((value: number, axis: number) => expect(value).toBeCloseTo(drawn[side][axis], 9));
  }
}

// Frames every 16 ms on the (fake) timers, stamped with the (fake) clock the ease reads.
function stubFrames() {
  const { requestAnimationFrame, cancelAnimationFrame } = window;
  window.requestAnimationFrame = (step) => setTimeout(() => step(performance.now()), 16) as unknown as number;
  window.cancelAnimationFrame = (id) => clearTimeout(id);
  return () => {
    window.requestAnimationFrame = requestAnimationFrame;
    window.cancelAnimationFrame = cancelAnimationFrame;
  };
}

// The stage (the lights, the key's shadow, the depth range) is fitted to the scene's bounds, which
// follow a pose because the pose pass refreshes them. The pose pass runs before this layer in a
// commit, so an explosion applied after it left the stage lighting the model as it had been: a
// snapshot of the same exploded view, whose stage is fitted to where the parts are, lit it differently.
it('an exploded view takes the stage with it: the scene is bounded where its parts are drawn, and the viewport refits', () => {
  const { cadScene, rest, syncSceneBounds, layers } = twoPartView();
  renderHook(() => useStepExplode(layers({ amount: 1 })));
  try {
    const drawn = drawnBox(cadScene);
    expect(drawn.max[0] - drawn.min[0]).toBeGreaterThan(rest.max[0] - rest.min[0]);
    expectBoundedWhereDrawn(cadScene);
    expect(syncSceneBounds).toHaveBeenCalled();
  } finally {
    cadScene.dispose();
  }
});

// An ease steps every frame for a second or more, and refitting the stage on each step measures every
// record each frame. The stage follows an ease at most every 100 ms, and is refitted where it ends.
it('an eased explosion refits its stage at most every 100 ms, and once more where it ends', () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance', 'Date'] });
  const restoreFrames = stubFrames();
  const { cadScene, syncSceneBounds, explosionRef, layers } = twoPartView();
  // The view is open on this model with the explosion off, and is turned on.
  explosionRef.current.modelKey = 'two-parts';
  const { rerender } = renderHook(({ active }) => useStepExplode(layers({ amount: 1, active })), { initialProps: { active: false } });
  try {
    rerender({ active: true });
    vi.advanceTimersByTime(500);
    expect(explosionRef.current.progress).toBeGreaterThan(0);
    expect(explosionRef.current.progress).toBeLessThan(1);
    // Half a second of ease, about 30 frames: refitted at its start and about every 100 ms.
    expect(syncSceneBounds.mock.calls.length).toBeLessThanOrEqual(7);
    vi.advanceTimersByTime(600);
    expect(explosionRef.current.progress).toBe(1);
    expect(syncSceneBounds.mock.calls.length).toBeLessThanOrEqual(13);
    expectBoundedWhereDrawn(cadScene);
  } finally {
    restoreFrames();
    cadScene.dispose();
  }
});

// Turning the view on eases the parts out over a second, and turning it off eases them back. The scene sync
// answers the commit that turns the view on or off with a new `displayRecordsToken`, which ran this layer
// again a frame or two into the ease, and that run snapped the parts to the end: neither ease ever showed.
it('turning the view on or off eases the parts the whole way, through the scene sync running it again', () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance', 'Date'] });
  const restoreFrames = stubFrames();
  const { cadScene, rest, syncSceneBounds, explosionRef, layers } = twoPartView();
  // The view is open on this model with the explosion off.
  explosionRef.current.modelKey = 'two-parts';
  const { rerender } = renderHook((props: { active: boolean, token: number }) => useStepExplode(layers({ amount: 1, ...props })),
    { initialProps: { active: false, token: 1 } });
  const width = () => drawnBox(cadScene).max[0] - drawnBox(cadScene).min[0];
  const restWidth = rest.max[0] - rest.min[0];
  try {
    // On, and the scene sync's new records token three frames in.
    rerender({ active: true, token: 1 });
    vi.advanceTimersByTime(48);
    rerender({ active: true, token: 2 });
    vi.advanceTimersByTime(48);
    expect(explosionRef.current.progress).toBeGreaterThan(0);
    expect(explosionRef.current.progress).toBeLessThan(0.5);
    expect(width()).toBeGreaterThan(restWidth);
    const refits = syncSceneBounds.mock.calls.length;
    vi.advanceTimersByTime(1000);
    expect(explosionRef.current.progress).toBe(1);
    expectBoundedWhereDrawn(cadScene);
    // A second of ease refits its stage about every 100 ms and once where it ends, not on every frame.
    expect(syncSceneBounds.mock.calls.length - refits).toBeLessThanOrEqual(12);
    const explodedWidth = width();

    // Off, and the token again.
    rerender({ active: false, token: 2 });
    vi.advanceTimersByTime(48);
    rerender({ active: false, token: 3 });
    vi.advanceTimersByTime(48);
    expect(explosionRef.current.progress).toBeLessThan(1);
    expect(explosionRef.current.progress).toBeGreaterThan(0.5);
    expect(width()).toBeLessThan(explodedWidth);
    expect(width()).toBeGreaterThan(restWidth);
    vi.advanceTimersByTime(1000);
    expect(explosionRef.current.progress).toBe(0);
    expect(width()).toBeCloseTo(restWidth, 9);
    expectBoundedWhereDrawn(cadScene);
  } finally {
    restoreFrames();
    cadScene.dispose();
  }
});
