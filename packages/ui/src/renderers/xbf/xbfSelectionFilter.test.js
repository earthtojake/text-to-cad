import assert from 'node:assert/strict';
import test from 'node:test';

import { nextSelectionIds } from './xbfSelectionFilter.js';

test("a plain pick of exactly what is selected lets it go, one element or a group; any other replaces it; Shift adds or takes away the group", () => {
  assert.deepEqual(nextSelectionIds(['f1'], ['f1']), []);
  // A tangent chain (Select tangent faces, Select tangent edges) or a folded row's parts, picked again while they are the selection.
  assert.deepEqual(nextSelectionIds(['f2', 'f1'], ['f1', 'f2']), []);
  // Not exactly what is selected: the pick replaces it.
  assert.deepEqual(nextSelectionIds(['f1'], ['f1', 'f2']), ['f1', 'f2']);
  assert.deepEqual(nextSelectionIds(['f1', 'f2', 'f3'], ['f1', 'f2']), ['f1', 'f2']);
  assert.deepEqual(nextSelectionIds(['f1'], []), []);
  // Additive: the group added, or taken away where every one of it is selected; nothing picked changes nothing.
  assert.deepEqual(nextSelectionIds(['f3'], ['f1', 'f2'], true), ['f3', 'f1', 'f2']);
  assert.deepEqual(nextSelectionIds(['f3', 'f1', 'f2'], ['f1', 'f2'], true), ['f3']);
  assert.deepEqual(nextSelectionIds(['f3'], [], true), ['f3']);
});
