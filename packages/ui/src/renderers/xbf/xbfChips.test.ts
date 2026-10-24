import { renderHook } from '@testing-library/react';
import { expect, it } from 'vitest';
import { parsePromptReference } from '@text-to-cad/core/prompt';
import { useXbfSelectionChips, xbfCopyText, xbfNodeRefs } from '../../../dist/renderers/xbf/xbfChips.js';
import { presentXbfTree, xbfCoveringIds } from '../../../dist/renderers/xbf/xbfTree.js';

// What an engine document's selection copies: the engine's canonical refs, one line each, the file's
// path first -- what `cadgen inspect DOC REF` and `select(DOC, REF)` read (cadgen.engine.refs) -- and
// what a paste of one names. A STEP drawn by the same renderer keeps its own grammar's references.

const part = (name: string, prototype: number, instance: number) => ({ name, prototype, instance });
// A palm, a hand of three fingers of one part, a screw whose label holds a slash, and a part whose
// label reads as a face's number.
const structure = {
  name: 'kit', version: '1-1', units: 'mm',
  prototypes: [
    { index: 0, key: 'k-palm', name: 'palm', faceNames: { 3: 'f:palm.body.3;M:palm.relief' }, edgeNames: {} },
    { index: 1, key: 'k-finger', name: 'finger', faceNames: { 1: 'f:finger.body.1' }, edgeNames: {} },
    { index: 2, key: 'k-screw', name: 'screw', faceNames: {}, edgeNames: { 2: 'e:screw.body.2' } },
  ] as any[],
  instances: ['kit/palm', 'kit/hand/finger', 'kit/hand/finger', 'kit/hand/finger', 'kit/M3/M4 screw', 'kit/face 3']
    .map((path, index) => ({ prototype: [0, 1, 1, 1, 2, 2][index], path, matrix: [], color: null })),
  tree: { name: 'kit', children: [
    part('palm', 0, 0),
    { name: 'hand', children: [part('finger', 1, 1), part('finger', 1, 2), part('finger', 1, 3)] },
    part('M3/M4 screw', 2, 4),
    part('face 3', 2, 5),
  ] },
};
const scene = {
  structure,
  describePart: (id: string) => ({ name: id }),
  describeElement: (id: string) => {
    const [, instance, kind, ordinal] = /^i(\d+)\/(face|edge)\/(\d+)$/.exec(id) || [];
    if (!instance) return null;
    const prototype = structure.prototypes[structure.instances[Number(instance)].prototype];
    return { id, kind, ordinal: Number(ordinal), instance: Number(instance), key: prototype.key,
      name: prototype[`${kind}Names`][ordinal] || '', path: structure.instances[Number(instance)].path };
  },
  measureParts: () => null,
};
const tree = presentXbfTree(structure);
const at = (path: string) => ({ kind: 'workspace-file', path });
const copied = (resource: object, ids: string[]) => xbfCopyText({ scene, tree, resource, ids }).split('\n');

it("an .xbf's selection copies the engine's canonical refs: a label, an occurrence path, an element by name or number", () => {
  const resource = at('/work/XBF/kit.xbf');
  expect(copied(resource, ['i0', 'n0.1', 'i2', 'i0/face/3', 'i2/face/1', 'i2/face/7', 'i4/edge/2', 'i5/face/3'])).toEqual([
    '/work/XBF/kit.xbf#palm',
    '/work/XBF/kit.xbf#hand',
    '/work/XBF/kit.xbf#kit/hand/finger.2',
    '/work/XBF/kit.xbf#palm/f:palm.body.3;M:palm.relief',
    '/work/XBF/kit.xbf#kit/hand/finger.2/f:finger.body.1',
    '/work/XBF/kit.xbf#kit/hand/finger.2/face 7',
    '/work/XBF/kit.xbf#"M3/M4 screw"/e:screw.body.2',
    '/work/XBF/kit.xbf#"face 3"/face 3',
  ]);
  // A pasted line is the reference it was copied from, and names the chip that copied it.
  const { result } = renderHook(() => useXbfSelectionChips({ scene, tree, resource, selectedIds: ['i2/face/1', 'i2/face/7'],
    facts: new Map(), onRemove: () => {}, onHover: () => {} }));
  const { chips, references } = result.current;
  expect(references.map((reference: any) => parsePromptReference(`${resource.path}#${reference.target.selectors[0]}`))).toEqual(references);
  expect(chips.map((chip: any) => chip.selectors)).toEqual([['kit/hand/finger.2/f:finger.body.1', 'kit/hand/finger.2/face 7']]);
});

it('a model the engine holds by its id is referenced by that id, in the engine grammar, and its chips copy', () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const resource = { kind: 'cad-model', path: id };
  expect(copied(resource, ['i0', 'i2/face/7'])).toEqual([`${id}#palm`, `${id}#kit/hand/finger.2/face 7`]);
  const { result } = renderHook(() => useXbfSelectionChips({ scene, tree, resource, selectedIds: ['i2/face/7'],
    facts: new Map(), onRemove: () => {}, onHover: () => {} }));
  expect(result.current.references).toEqual([{ resource, target: { kind: 'cad-selector', selectors: ['kit/hand/finger.2/face 7'] } }]);
});

it('a view hides and isolates by the refs Copy Prompt copies, a hidden assembly by its own', () => {
  const resource = at('/work/XBF/kit.xbf');
  const refs = (ids: string[]) => xbfNodeRefs({ scene, tree, resource, ids });
  expect(refs(xbfCoveringIds(tree, ['i3', 'i5', 'i1', 'i2']))).toEqual(['/work/XBF/kit.xbf#hand', '/work/XBF/kit.xbf#"face 3"']);
  expect(refs(xbfCoveringIds(tree, ['i2', 'i0']))).toEqual(copied(resource, ['i0', 'i2']));
  expect(refs(['n0.1', 'i4'])).toEqual(copied(resource, ['n0.1', 'i4']));
  expect(xbfCoveringIds(tree, [])).toEqual([]);
});

it('a STEP drawn by the engine keeps its own grammar\'s references', () => {
  const step = at('/work/STEP/kit.step');
  expect(copied(step, ['i0', 'i0/face/3'])).toEqual(['/work/STEP/kit.step#palm', '/work/STEP/kit.step#palm/f:palm.body.3;M:palm.relief']);
  // An element its names do not spell is no reference there: its part's path, its kind and number.
  expect(copied(step, ['i0/face/2'])).toEqual(['kit/palm face 2']);
});
