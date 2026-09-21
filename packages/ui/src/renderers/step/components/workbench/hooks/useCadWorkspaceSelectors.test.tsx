import { cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useCadWorkspaceSelectors } from '../../../../../../dist/renderers/step/components/workbench/hooks/useCadWorkspaceSelectors.js';

afterEach(() => cleanup());

// Everything the workspace tells the viewport about parts and references is derived from the
// two lists this hook publishes. A render that changes nothing must therefore change no
// identity: a fresh `[]` carrying the same contents re-ran the reference maps, then the
// render-part id lists built on them, then every viewport layer keyed on one of those — part
// visual state over every display record among them — on a pose, a hover, a status tick. The
// viewport held that back with a comparison of its own, which hid the churn upstream and left
// a memo load-bearing for how much work happens rather than for how fast it is.
//
// What the caller owns (the selected and hovered ids) is React state and keeps its identity
// on its own; what this hook derives is what these tests are about.

const EMPTY: never[] = [];
const reference = (id: string, selectorType = 'face') => ({ id, selectorType, displaySelector: id, normalizedSelector: id });
const inputs = (overrides: Record<string, unknown> = {}) => ({
  selectedReferencesMatch: false,
  referenceState: null,
  isAssemblyView: true,
  supportsPartSelection: false,
  assemblyParts: undefined,
  assemblyPartMap: undefined,
  inspectedAssemblyNodeId: '',
  inspectedAssemblyPartTopologyReferences: EMPTY,
  selectedReferenceIds: EMPTY,
  selectedPartIds: EMPTY,
  hoveredListReferenceId: '',
  hoveredModelReferenceId: '',
  hoveredListPartId: '',
  hoveredModelPartId: '',
  ...overrides
});
const NAMES = ['currentReferences', 'activeReferenceMap', 'referenceMap', 'visibleReferences', 'filteredReferences',
  'assemblyParts', 'assemblyPartMap', 'selectedReferences', 'selectedParts', 'inspectedAssemblyPartReferences'];
const identities = (result: any) => NAMES.map(name => result[name]);
/**
 * IDENTITY, not contents. Two empty lists are equal and are not the same list, and it is
 * sameness this is about — every consumer downstream is memoized on the reference.
 */
const held = (result: any, before: unknown[], what: string) =>
  NAMES.forEach((name, index) => expect(result[name], `${name} ${what}`).toBe(before[index]));

it('a file with no topology loaded re-renders without changing one identity', () => {
  const { result, rerender } = renderHook(props => useCadWorkspaceSelectors(props), { initialProps: inputs() });
  const before = identities(result.current);
  expect(result.current.currentReferences).toEqual([]);
  // A fresh props OBJECT is what a parent render produces; its contents have not changed.
  rerender(inputs());
  held(result.current, before, 'survives a render that changed nothing');
  // Nor does a change that has nothing to do with these lists.
  rerender(inputs({ hoveredModelPartId: 'o1.1' }));
  held(result.current, before, 'survives a hover');
});

it('references that arrive change the lists once, and hold their identity after', () => {
  const references = [reference('o1.1:f1'), reference('o1.1:f2')];
  const loaded = inputs({ selectedReferencesMatch: true, referenceState: { references } });
  const { result, rerender } = renderHook(props => useCadWorkspaceSelectors(props), { initialProps: inputs() });
  const empty = result.current.currentReferences;
  rerender(loaded);
  expect(result.current.currentReferences).toBe(references);
  expect(result.current.currentReferences).not.toBe(empty);
  const loadedIdentities = identities(result.current);
  rerender({ ...loaded, referenceState: { references } });
  held(result.current, loadedIdentities, 'survives a render once the references are in');
  // A revision that really does replace them is not held back.
  rerender({ ...loaded, referenceState: { references: [reference('o1.1:f1')] } });
  expect(result.current.currentReferences).not.toBe(references);
  expect(result.current.activeReferenceMap).not.toBe(loadedIdentities[1]);
});

it('a selection resolves against the loaded references and keeps its identity while it stands', () => {
  const references = [reference('o1.1:f1'), reference('o1.1:f2')];
  const selected = inputs({ selectedReferencesMatch: true, referenceState: { references }, selectedReferenceIds: ['o1.1:f2'] });
  const { result, rerender } = renderHook(props => useCadWorkspaceSelectors(props), { initialProps: selected });
  expect(result.current.selectedReferences.map((item: any) => item.id)).toEqual(['o1.1:f2']);
  expect(result.current.hoveredReference).toBe(null);
  const resolved = result.current.selectedReferences;
  rerender({ ...selected, hoveredModelPartId: 'o1.1' });
  expect(result.current.selectedReferences).toBe(resolved);
});
