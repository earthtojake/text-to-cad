import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';
import { stripTypeScriptTypes } from 'node:module';

// The live `select` is StepSurface's own: it resolves selectors, sets the selection, and hands the
// binding the predicate for the set it resolved. The binding-level test mocks that predicate, so
// this one runs the real method body, lifted out of the component, against a fake scope.

// The real predicate, from live.ts with its types stripped (its imports are type-only).
const { selectionCommitted } = await import(`data:text/javascript,${encodeURIComponent(stripTypeScriptTypes(fs.readFileSync(new URL('./live.ts', import.meta.url), 'utf8')))}`);
const traverse = traverseModule.default || traverseModule;
const source = fs.readFileSync(new URL('./StepSurface.jsx', import.meta.url), 'utf8');
let selectCommand;
traverse(parse(source, { sourceType: 'module', plugins: ['jsx'] }), {
  ObjectMethod(path) {
    if (path.node.key.name !== 'select' || path.parent.type !== 'ObjectExpression') return;
    selectCommand = Function('scope', 'options', `with (scope) { return (function(${source.slice(path.node.params[0].start, path.node.params[0].end)}) ${source.slice(path.node.body.start, path.node.body.end)})(options); }`);
  }
});
assert.ok(selectCommand, 'StepSurface exposes a live select');

function scope(previous) {
  const set = {};
  return {
    set,
    scope: {
      uniqueStringList: list => [...new Set(list)],
      resolveSelectorSelection: name => ({ kind: 'part', id: name }),
      effectiveActiveReferenceMap: new Map(), displayStepTreeRoot: {}, stepTreeRoot: {},
      isAssemblyView: true, validAssemblySelectionIdSet: new Set(['part-a', 'part-b', 'extra']),
      selectedPartIdsRef: { current: previous }, selectedReferenceIdsRef: { current: [] },
      selectedRenderPartIdByAssemblyPartIdRef: { current: {} },
      setSelectedPartIds: ids => { set.parts = ids; }, setSelectedReferenceIds: ids => { set.references = ids; },
      setSelectedRenderPartIdByAssemblyPartId: map => { set.render = map; },
      renderPartIdForAssemblySelection: id => `render:${id}`,
      // The viewer's ids for a selection: what `selectedPartIds` of the live state holds.
      viewerPartIdsForSelection: (parts, _references, renderIds) => parts.map(id => renderIds[id] ?? id),
      revealStepTreeNode() {}, findStepTreeTopologyNodeIdForReference: () => null, referencePartId: () => null,
      selectionCommitted
    }
  };
}
const held = (ids) => ({ selection: ids.map(id => ({ id })), selectedPartIds: ids, selectedReferenceIds: [] });

test('a replacing part-only select is committed only when the live selection is exactly the new part', () => {
  const view = scope(['part-a', 'extra']);
  const committed = selectCommand(view.scope, { selectors: ['part-b'], replace: true });
  assert.equal(typeof committed, 'function', 'the command hands the binding its predicate');
  assert.deepEqual(view.set.parts, ['part-b']);
  assert.equal(committed(held(['part-a', 'extra'])), false, 'the old non-empty selection does not answer for the new one');
  assert.equal(committed(held(['render:part-b', 'extra'])), false, 'the new part plus a leftover is not the set');
  assert.equal(committed(held([])), false, 'nothing is not it either');
  assert.equal(committed(held(['render:part-b'])), true, 'exactly the new part, as the viewer names it');
});
