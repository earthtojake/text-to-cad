import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useModelTools } from '../../../../../dist/renderers/step/components/workbench/ModelTools.js';

afterEach(cleanup);
const neutral = () => ({ exploded: { enabled: false, amount: 0 }, clip: { enabled: false, axis: 'x', offsets: { x: 1, y: 1, z: 1 }, invert: false } });

it('retains only applied effects after leaving and follows external resets and file changes', () => {
  const props = { modelKey: 'one', view: neutral(), features: { sections: ['exploded', 'clip'] }, store: { patch: vi.fn() },
    mesh: null, disabled: false, selectedTool: 'exploded', onSelect: vi.fn() };
  const { result, rerender } = renderHook(options => useModelTools(options), { initialProps: props });
  const active = () => result.current.tools.filter(tool => tool.active).map(tool => tool.id);
  act(() => result.current.tools.find(tool => tool.id === 'exploded').onSelect());
  expect(active()).toEqual(['exploded']);
  rerender({ ...props, selectedTool: 'references' });
  expect(active()).toEqual([]);
  const applied = { ...props, selectedTool: 'references', view: { ...neutral(), exploded: { enabled: true, amount: .4 } } };
  rerender(applied);
  expect(active()).toEqual(['exploded']);
  rerender({ ...applied, view: neutral() });
  expect(active()).toEqual([]);
  rerender(applied);
  rerender({ ...props, modelKey: 'two', selectedTool: 'references' });
  expect(active()).toEqual([]);
});

it('returning a clip to zero removes its panel when another tool is chosen', () => {
  const props = { modelKey: 'one', view: { ...neutral(), clip: { ...neutral().clip, enabled: true, offsets: { x: .5, y: 1, z: 1 } } },
    features: { sections: ['clip'] }, store: { patch: vi.fn() }, mesh: null, disabled: false, selectedTool: 'clip', onSelect: vi.fn() };
  const { result, rerender } = renderHook(options => useModelTools(options), { initialProps: props });
  expect(result.current.tools[0].active).toBe(true);
  rerender({ ...props, view: neutral() });
  expect(result.current.tools[0].active).toBe(true);
  rerender({ ...props, view: neutral(), selectedTool: 'display' });
  expect(result.current.tools[0].active).toBe(false);
});

it('offers Explode only where there are parts to separate, and idles it while that is unknown', () => {
  const part = (id: string) => ({ id, bounds: { min: [0, 0, 0], max: [1, 1, 1] } });
  const props = { modelKey: 'one', view: neutral(), features: { sections: ['exploded', 'clip'] }, store: { patch: vi.fn() },
    mesh: null as null | object, disabled: true, selectedTool: 'references', onSelect: vi.fn() };
  const { result, rerender } = renderHook(options => useModelTools(options), { initialProps: props });
  const offered = () => result.current.tools.map(tool => `${tool.id}:${tool.disabled}`);
  // Loading: nothing is known about the parts yet, so the strip shows Explode, idle.
  expect(offered()).toEqual(['exploded:true', 'clip:true']);
  // A single part has nothing to separate: Explode is not on the strip at all, never disabled.
  rerender({ ...props, disabled: false, mesh: { parts: [part('a')] } });
  expect(offered()).toEqual(['clip:false']);
  rerender({ ...props, disabled: false, mesh: { parts: [part('a'), part('b')] } });
  expect(offered()).toEqual(['exploded:false', 'clip:false']);
});
