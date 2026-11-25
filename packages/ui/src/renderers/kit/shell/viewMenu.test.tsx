import { expect, it, vi } from 'vitest';
import { menuGroups, pickGroup, referenceGroup, zoomGroup } from '../../../../dist/renderers/kit/shell/viewMenu.js';
import { sceneMenuEntries } from '../../../../dist/renderers/kit/tools/select/sceneMenu.js';

const shape = (entries: any[]) => entries.map(entry => [entry.id, entry.disabled, entry.separatorBefore]);

it('every view menu is its groups in one order, a rule between groups, the framing last and Zoom to selection off with nothing picked', () => {
  const entries = menuGroups(referenceGroup({ copyText: '' }), pickGroup({ selected: true, isolated: false, onIsolate: () => {}, isolatedCount: 2, onExitIsolates: () => {} }),
    [], zoomGroup({ onZoomFit: () => {}, onZoomSelection: () => {}, selectionAvailable: false }));
  expect(shape(entries)).toEqual([
    ['copy-reference', true, false],
    ['select', false, true], ['isolate', false, false], ['exit-all-isolates', false, false],
    ['zoom-fit', false, true], ['zoom-selection', true, false]
  ]);
});

it("a 3D scene's menu: the framing over empty space; over a pick its reference, Select or Deselect, the renderer's own, and the framing", () => {
  const viewer = { resetZoom: vi.fn(), zoomToBounds: vi.fn() };
  const box = { min: [0, 0, 0], max: [1, 1, 1] };
  let hit: any = null;
  const scene = { pick: () => hit, selectionBounds: vi.fn(() => box) };
  class Raycaster { ray = {}; setFromCamera() {} }
  class Vector2 { constructor(public x = 0, public y = 0) {} }
  const viewport = { runtimeRef: { current: { camera: { updateMatrixWorld() {} }, THREE: { Raycaster, Vector2 } } },
    hostRef: { current: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 100 }) } } };
  const menu = (selected: string[], more?: any) => sceneMenuEntries({ press: { clientX: 50, clientY: 50 }, viewport, scene, selected, t: (key: string) => key,
    copyText: (picked: any) => `@file#${picked.id}`, onCopy: vi.fn(), onSelect: vi.fn(), viewer: () => viewer, more });
  expect(menu([]).map(entry => entry.id)).toEqual(['zoom-fit', 'zoom-selection']);
  menu([])[0].onSelect();
  expect(viewer.resetZoom).toHaveBeenCalledTimes(1);
  hit = { id: 'n2' };
  const over = menu(['n2'], () => [{ id: 'visibility', label: 'Hide' }]);
  expect(over.map(entry => entry.id)).toEqual(['copy-reference', 'select', 'visibility', 'zoom-fit', 'zoom-selection']);
  expect(over[1].label.props.children).toBe('menu.deselect');
  over.at(-1).onSelect();
  expect(scene.selectionBounds).toHaveBeenCalledWith(['n2']);
  expect(viewer.zoomToBounds).toHaveBeenCalledWith(box);
});
