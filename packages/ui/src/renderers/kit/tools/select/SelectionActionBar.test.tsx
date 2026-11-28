import React from 'react';
import { act, cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import SelectionActionBar, { placeBar } from '../../../../../dist/renderers/kit/tools/select/SelectionActionBar.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../../dist/host/testing/host.js';

afterEach(cleanup);
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any;

const room = { width: 400, height: 300, top: 56, bottom: 240 };

// Above the pick where there is room, else below it, else at the top of the room; always inside the room the strip's
// column and Quick Edit leave, and nowhere at all while the pick is off the view.
it('stands just above the pick, else below it, inside the room the chrome leaves', () => {
  const size = { width: 100, height: 24 };
  expect(placeBar({ left: 150, right: 250, top: 150, bottom: 200 }, size, room)).toEqual({ left: 150, top: 116 });
  expect(placeBar({ left: 150, right: 250, top: 70, bottom: 120 }, size, room)).toEqual({ left: 150, top: 130 });
  expect(placeBar({ left: 0, right: 400, top: 40, bottom: 260 }, size, room)).toEqual({ left: 150, top: 56 });
  expect(placeBar({ left: -60, right: 20, top: 150, bottom: 200 }, size, room)).toEqual({ left: 8, top: 116 });
  expect(placeBar({ left: 500, right: 600, top: 150, bottom: 200 }, size, room)).toBeNull();
  expect(placeBar(null, size, room)).toBeNull();
});

// What it offers is the renderer's actions, and nothing else: the rest is the view's menu.
it("offers the renderer's actions alone", async () => {
  // Every corner of the box falls on the view's middle (projecting it needs a real camera: mocked below).
  const camera = { updateMatrixWorld() {} };
  const runtime = { camera, renderer: { domElement: document.createElement('canvas') } };
  Object.defineProperty(runtime.renderer.domElement, 'clientWidth', { value: 400 });
  Object.defineProperty(runtime.renderer.domElement, 'clientHeight', { value: 300 });
  vi.spyOn((await import('three')).Vector3.prototype, 'project').mockImplementation(function (this: any) { this.set(0, 0, 0); return this; });
  const hide = vi.fn(), isolate = vi.fn();
  await act(async () => {
    render(<ViewerHostContext.Provider value={testHost()}>
      <SelectionActionBar runtimeRef={{ current: runtime }} bounds={() => ({ min: [0, 0, 0], max: [1, 1, 1] })} boundsKey="i1"
        label="Selection actions"
        actions={[{ id: 'isolate', label: 'Isolate', icon: null, onSelect: isolate }, { id: 'hide', label: 'Hide', icon: null, onSelect: hide }]} />
    </ViewerHostContext.Provider>);
  });
  const bar = await screen.findByRole('toolbar', { name: 'Selection actions' });
  const controls = [...bar.querySelectorAll('button, [role=separator]')]
    .map(element => (element.getAttribute('role') === 'separator' ? '|' : element.getAttribute('aria-label')));
  expect(controls).toEqual(['Isolate', 'Hide']);
  within(bar).getByRole('button', { name: 'Hide' }).click();
  expect(hide).toHaveBeenCalledTimes(1);
  within(bar).getByRole('button', { name: 'Isolate' }).click();
  expect(isolate).toHaveBeenCalledTimes(1);
});
