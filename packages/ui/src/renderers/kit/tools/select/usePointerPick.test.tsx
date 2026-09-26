import React from 'react';
import * as THREE from 'three';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PointerPick } from '../../../../../dist/renderers/kit/tools/select/usePointerPick.js';

Object.assign(globalThis, { React });
let frames: FrameRequestCallback[] = [];
beforeEach(() => {
  frames = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.push(callback); return frames.length; });
  vi.stubGlobal('cancelAnimationFrame', () => {});
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const frame = () => { const due = frames; frames = []; due.forEach(callback => callback(0)); };

function mount(props: Record<string, unknown> = {}) {
  const host = document.body.appendChild(document.createElement('div'));
  const canvas = host.appendChild(document.createElement('canvas'));
  const control = host.appendChild(document.createElement('button'));
  host.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100, right: 200, bottom: 100, x: 0, y: 0, toJSON() {} });
  const camera = new THREE.OrthographicCamera(-2, 2, 1, -1, 0.1, 10);
  camera.position.set(0, 0, 5);
  const viewport = { runtimeRef: { current: { THREE, camera, renderer: { domElement: canvas } } }, hostRef: { current: host }, viewerReadyTick: 1 };
  // Whatever is under the left half of the picture is "left"; the right half is empty.
  const scene = { pick: vi.fn((ray: THREE.Ray) => (ray.origin.x < 0 ? { id: 'left', point: ray.origin.clone() } : null)) };
  const onPick = vi.fn(), onHover = vi.fn();
  const view = render(<PointerPick viewport={viewport} scene={scene} enabled onPick={onPick} onHover={onHover} {...props}/>);
  const fire = (target: Element, type: string, init: PointerEventInit) => target.dispatchEvent(new PointerEvent(type, { bubbles: true, pointerId: 1, button: 0, pointerType: 'mouse', ...init }));
  return { host, canvas, control, scene, onPick, onHover, fire, viewport, rerender: (next: Record<string, unknown>) => view.rerender(<PointerPick viewport={viewport} scene={scene} enabled onPick={onPick} onHover={onHover} {...next}/>) };
}

it('a tap picks at once through the scene contract; Shift adds; a drag is the camera\'s', () => {
  const { canvas, control, onPick, fire } = mount();
  fire(canvas, 'pointerdown', { clientX: 50, clientY: 50 });
  fire(canvas, 'pointerup', { clientX: 52, clientY: 51 });
  expect(onPick).toHaveBeenCalledTimes(1);
  expect(onPick.mock.calls[0][0].id).toBe('left');
  expect(onPick.mock.calls[0][1]).toEqual({ multiSelect: false });
  fire(canvas, 'pointerdown', { clientX: 150, clientY: 50 });
  fire(canvas, 'pointerup', { clientX: 150, clientY: 50, shiftKey: true });
  expect(onPick.mock.calls[1]).toEqual([null, { multiSelect: true }]);
  // Past the tap slop the press was an orbit; a press on a control over the canvas is that control's.
  fire(canvas, 'pointerdown', { clientX: 50, clientY: 50 });
  fire(canvas, 'pointerup', { clientX: 60, clientY: 50 });
  fire(control, 'pointerdown', { clientX: 50, clientY: 50 });
  fire(control, 'pointerup', { clientX: 50, clientY: 50 });
  fire(canvas, 'pointerdown', { clientX: 50, clientY: 50, button: 2 });
  fire(canvas, 'pointerup', { clientX: 50, clientY: 50, button: 2 });
  expect(onPick).toHaveBeenCalledTimes(2);
  // A finger gets a wider slop.
  fire(canvas, 'pointerdown', { clientX: 50, clientY: 50, pointerType: 'touch' });
  fire(canvas, 'pointerup', { clientX: 59, clientY: 50, pointerType: 'touch' });
  expect(onPick).toHaveBeenCalledTimes(3);
});

it('hover is one pick per frame, reported on change, with the cursor saying so', () => {
  const { host, canvas, scene, onHover, fire } = mount();
  fire(canvas, 'pointermove', { clientX: 40, clientY: 50 });
  fire(canvas, 'pointermove', { clientX: 45, clientY: 50 });
  expect(scene.pick).not.toHaveBeenCalled();
  frame();
  expect(scene.pick).toHaveBeenCalledTimes(1);
  expect(onHover.mock.calls.map(([hit]) => hit?.id ?? null)).toEqual(['left']);
  expect(host.style.cursor).toBe('pointer');
  fire(canvas, 'pointermove', { clientX: 46, clientY: 50 });
  frame();
  expect(scene.pick).toHaveBeenCalledTimes(1);
  fire(canvas, 'pointermove', { clientX: 60, clientY: 50 });
  frame();
  expect(onHover).toHaveBeenCalledTimes(1);
  // A camera gesture under way is not a hover.
  fire(canvas, 'pointermove', { clientX: 150, clientY: 50, buttons: 1 });
  frame();
  expect(onHover).toHaveBeenCalledTimes(1);
  fire(canvas, 'pointermove', { clientX: 150, clientY: 50 });
  frame();
  expect(onHover.mock.calls.map(([hit]) => hit?.id ?? null)).toEqual(['left', null]);
  expect(host.style.cursor).toBe('');
});

it('listens only while enabled, and leaves nothing hovered behind', () => {
  const { host, canvas, onPick, onHover, fire, rerender } = mount();
  fire(canvas, 'pointermove', { clientX: 40, clientY: 50 });
  frame();
  expect(host.style.cursor).toBe('pointer');
  rerender({ enabled: false });
  expect(onHover.mock.calls.at(-1)).toEqual([null]);
  expect(host.style.cursor).toBe('');
  fire(canvas, 'pointerdown', { clientX: 50, clientY: 50 });
  fire(canvas, 'pointerup', { clientX: 50, clientY: 50 });
  expect(onPick).not.toHaveBeenCalled();
});

it('pinch, cancelled touches, and a drag returning to its start never become picks', () => {
  const { canvas, onPick, fire } = mount();
  const touch = (type: string, pointerId = 1, clientX = 50) => fire(canvas, type, { pointerType: 'touch', pointerId, clientX, clientY: 50 });
  touch('pointerdown');
  touch('pointerdown', 2, 80);
  touch('pointerup', 2, 80);
  touch('pointerup');
  touch('pointerdown');
  touch('pointercancel');
  touch('pointerup');
  touch('pointerdown');
  touch('pointermove', 1, 90);
  touch('pointermove');
  touch('pointerup');
  expect(onPick).not.toHaveBeenCalled();
  touch('pointerdown');
  touch('pointerup');
  expect(onPick).toHaveBeenCalledTimes(1);
});
