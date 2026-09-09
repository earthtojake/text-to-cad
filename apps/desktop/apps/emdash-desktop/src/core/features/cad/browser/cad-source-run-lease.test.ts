import { describe, expect, it } from 'vitest';
import { ensureCadModel, type CadModelIdentity } from '@core/features/cad/api/cad-model-state';
import type { CadModelCatalog } from '@core/features/cad/contributions/mementos';
import type { MementoSetter } from '@core/primitives/mementos/react/use-memento';
import { acquireCadSourceRunLease } from './cad-source-run-lease';

const identity: CadModelIdentity = {
  contextKey: 'cad-model:parts/plate',
  modelPath: 'parts/plate.step',
  sourcePath: 'recipes/plate.py',
};
const startedAt = '2026-08-29T12:00:00.000Z';

describe('CAD source run lease', () => {
  it('atomically rejects a second direct edit while the first owns the model', () => {
    let catalog = ensureCadModel(
      { version: '3', models: {} },
      identity,
      '2026-08-29T11:59:00.000Z'
    );
    const updateCatalog: MementoSetter<CadModelCatalog> = (next) => {
      catalog = typeof next === 'function' ? next(catalog) : next;
    };

    expect(acquireCadSourceRunLease(updateCatalog, identity, { id: 'source-1', startedAt })).toBe(
      true
    );
    const firstLease = catalog;

    expect(
      acquireCadSourceRunLease(updateCatalog, identity, {
        id: 'source-2',
        startedAt: '2026-08-29T12:00:01.000Z',
      })
    ).toBe(false);
    expect(catalog).toBe(firstLease);
    expect(catalog.models[identity.contextKey]?.run).toMatchObject({
      id: 'source-1',
      origin: 'source',
      status: 'generating',
    });
  });
});
