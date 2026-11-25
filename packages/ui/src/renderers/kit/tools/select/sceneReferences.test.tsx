import { renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { formatPromptReference } from '@cad/core/prompt';
import { sceneCopyText, useSceneReferences } from '../../../../../dist/renderers/kit/tools/select/sceneReferences.js';

const FILE = { kind: 'workspace-file', path: '/work/cart.3mf' };
// The picks of a 3MF or a GLB are dotted paths (`o2.1`); the ids a file's grammar cannot name are what a view
// should never have handed over, and what it must survive if it does.
const GOOD = ['o1', 'o2.1', 'n3'];
const UNNAMEABLE = ['wheel 1', 'o2-1', '2.1', 'o2..1', 'wheel#1'];

const mount = (selected: string[], resource: unknown = FILE) => {
  const select = vi.fn(), hover = vi.fn();
  const scene = { describePart: (id: string) => ({ name: `part ${id}`, facts: [] }) };
  return { select, hover, ...renderHook(() => useSceneReferences({ scene, selection: { selected, select, hover } as never, resource: resource as never })) };
};

it('a pick the file can name is a chip that copies its reference, and one Quick Edit carries', () => {
  const { result } = mount(GOOD);
  expect(result.current.chips.map(chip => chip.copy)).toEqual(GOOD.map(id => `/work/cart.3mf#${id}`));
  expect(result.current.references.map(reference => reference.target.selectors)).toEqual(GOOD.map(id => [id]));
});

it.each(UNNAMEABLE)('a pick the file cannot name (%s) is a chip with nothing to copy, not an error that takes the view down', (id) => {
  // `formatPromptReference` refuses it, and it ran inside the hook's `useMemo`: the throw unmounted the view.
  expect(() => formatPromptReference({ resource: FILE, target: { kind: 'cad-selector', selectors: [id] } } as never)).toThrow(/Invalid prompt context/);
  const { result } = mount(['o1', id]);
  expect(result.current.chips.map(chip => chip.id)).toEqual(['o1', id]);
  expect(result.current.chips.map(chip => chip.copy)).toEqual(['/work/cart.3mf#o1', undefined]);
  expect(result.current.references.map(reference => reference.target.selectors[0])).toEqual(['o1']);
  result.current.chips[1].onRemove();
  expect(result.current.chips[1].label).toBe(`part ${id}`);
});

it('a file the host names by a path that is not absolute has chips and no references', () => {
  const { result } = mount(['o1'], { kind: 'workspace-file', path: 'C:\\work\\cart.3mf' });
  expect(result.current.chips.map(chip => [chip.id, chip.copy])).toEqual([['o1', undefined]]);
  expect(result.current.references).toEqual([]);
});

it('Copy Reference on a selection with an unnameable pick copies nothing, and on the others what it names', () => {
  expect(sceneCopyText(FILE, ['o1', 'o2.1'])).toBe('/work/cart.3mf#o1,o2.1');
  expect(sceneCopyText(FILE, ['o1', 'wheel 1'])).toBe('');
  expect(sceneCopyText({ kind: 'url', url: 'https://example.com/a.3mf' } as never, ['o1'])).toBe('');
  expect(sceneCopyText(FILE, [])).toBe('');
});

it("where the host's prompts name the file otherwise (a shared model's link), a chip and Copy Reference copy that name, and the references stay the view's", () => {
  const link = 'https://cad.example/AbCdEfGhIjKlMnOpQrSt_-';
  const subject = { resource: { kind: 'url', url: link }, note: 'Shared.' };
  const select = vi.fn(), hover = vi.fn();
  const scene = { describePart: (id: string) => ({ name: `part ${id}`, facts: [] }) };
  const { result } = renderHook(() => useSceneReferences({ scene, selection: { selected: ['o1', 'wheel 1'], select, hover } as never,
    resource: FILE as never, subject: subject as never }));
  expect(result.current.chips.map(chip => chip.copy)).toEqual([`${link}#o1`, undefined]);
  expect(result.current.references).toEqual([{ resource: FILE, target: { kind: 'cad-selector', selectors: ['o1'] } }]);
  expect(sceneCopyText(FILE as never, ['o1', 'o2.1'], subject as never)).toBe(`${link}#o1,o2.1`);
  // What the file's own grammar cannot name copies nothing, whatever the host names the file by.
  expect(sceneCopyText(FILE as never, ['o1', 'wheel 1'], subject as never)).toBe('');
});
