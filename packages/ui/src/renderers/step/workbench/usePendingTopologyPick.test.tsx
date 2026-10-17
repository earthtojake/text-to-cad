import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { usePendingTopologyPick } from '../../../../dist/renderers/step/workbench/usePendingTopologyPick.js';

// The fixture's arm and base, and a face of each, as the view names them.
const ARM = 'o:5da881c8dcfe', BASE = 'o:cec517897e79';
const face = (part: string) => `topology|${part}|face|${part}/f:hinge_block.make_box1.6`;
const PRESS = { clientX: 529, clientY: 301, pointerType: 'mouse', multiSelect: false };

afterEach(cleanup);

/** The hook over a viewport whose raycast is `pickAtRef.current`, in a view whose parts' faces are `loaded`. */
function mount({ loaded = [] as string[], ready = true, failed = false } = {}) {
  const pickAtRef = { current: vi.fn(() => '') };
  const activate = vi.fn();
  const loadTopology = vi.fn();
  const hook = renderHook((props: { loadedIds: Set<string>; ready: boolean; failed: boolean }) => usePendingTopologyPick({
    pickAtRef, activate, loadTopology, isTopologyReference: (id: string) => id.startsWith('topology|'), ...props,
  }), { initialProps: { loadedIds: new Set(loaded), ready, failed } });
  return { ...hook, pickAtRef, activate, loadTopology };
}

it('a press on a part whose faces are still to load asks for them, and is picked again at the press point once they land', () => {
  const { result, rerender, pickAtRef, activate, loadTopology } = mount();
  act(() => result.current.press(ARM, PRESS));
  expect(loadTopology).toHaveBeenCalledWith([ARM]);
  expect(result.current.pending).toMatchObject({ partId: ARM, clientX: 529, clientY: 301 });
  expect(pickAtRef.current).not.toHaveBeenCalled();
  expect(activate).not.toHaveBeenCalled();
  pickAtRef.current.mockReturnValue(face(ARM));
  rerender({ loadedIds: new Set([ARM]), ready: true, failed: false });
  expect(pickAtRef.current).toHaveBeenCalledWith(529, 301, 'mouse');
  expect(activate).toHaveBeenCalledWith(face(ARM), { multiSelect: false });
  expect(result.current.pending).toBeNull();
});

it('a press on a part whose faces landed since its raycast is picked again at once, never dropped', () => {
  // The press's own raycast found the part; by its activation the view lists the part's faces.
  const { result, pickAtRef, activate } = mount({ loaded: [ARM] });
  pickAtRef.current.mockReturnValue(face(ARM));
  act(() => result.current.press(ARM, { ...PRESS, multiSelect: true }));
  expect(pickAtRef.current).toHaveBeenCalledWith(529, 301, 'mouse');
  expect(activate).toHaveBeenCalledWith(face(ARM), { multiSelect: true });
  expect(result.current.pending).toBeNull();
});

it('a press waits while the view is not ready, and is dropped by a load that fails or a point that reaches no face or edge', () => {
  const held = mount({ loaded: [ARM], ready: false });
  held.pickAtRef.current.mockReturnValue(face(ARM));
  act(() => held.result.current.press(ARM, PRESS));
  expect(held.activate).not.toHaveBeenCalled();
  held.rerender({ loadedIds: new Set([ARM]), ready: true, failed: false });
  expect(held.activate).toHaveBeenCalledWith(face(ARM), { multiSelect: false });

  const failing = mount();
  act(() => failing.result.current.press(ARM, PRESS));
  failing.rerender({ loadedIds: new Set(), ready: true, failed: true });
  expect(failing.result.current.pending).toBeNull();
  failing.pickAtRef.current.mockReturnValue(face(ARM));
  failing.rerender({ loadedIds: new Set([ARM]), ready: true, failed: false });
  expect(failing.activate).not.toHaveBeenCalled();

  const missed = mount({ loaded: [ARM] });
  missed.pickAtRef.current.mockReturnValue(ARM);
  act(() => missed.result.current.press(ARM, PRESS));
  expect(missed.activate).not.toHaveBeenCalled();
  expect(missed.result.current.pending).toBeNull();
});

it('one press waits at a time: the newest settles the one before it, and settle drops a waiting press', () => {
  const { result, rerender, pickAtRef, activate, loadTopology } = mount();
  act(() => result.current.press(ARM, PRESS));
  act(() => result.current.press(BASE, { ...PRESS, clientX: 310 }));
  expect(loadTopology.mock.calls).toEqual([[[ARM]], [[BASE]]]);
  pickAtRef.current.mockReturnValue(face(ARM));
  rerender({ loadedIds: new Set([ARM]), ready: true, failed: false });
  expect(activate).not.toHaveBeenCalled();
  pickAtRef.current.mockReturnValue(face(BASE));
  rerender({ loadedIds: new Set([ARM, BASE]), ready: true, failed: false });
  expect(pickAtRef.current).toHaveBeenCalledTimes(1);
  expect(pickAtRef.current).toHaveBeenCalledWith(310, 301, 'mouse');
  expect(activate).toHaveBeenCalledWith(face(BASE), { multiSelect: false });

  const settled = mount();
  act(() => settled.result.current.press(ARM, PRESS));
  act(() => settled.result.current.settle());
  expect(settled.result.current.pending).toBeNull();
  settled.pickAtRef.current.mockReturnValue(face(ARM));
  settled.rerender({ loadedIds: new Set([ARM]), ready: true, failed: false });
  expect(settled.activate).not.toHaveBeenCalled();
});
