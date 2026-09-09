import { describe, expect, it } from 'vitest';
import type { CadModelCatalog } from '@core/features/cad/contributions/mementos';
import {
  cadSourceRunHasRestorableFiles,
  resolveCadSourceRebuildModel,
} from './cad-source-rebuild-model';

describe('CAD source rebuild model resolution', () => {
  it('preserves an explicit source-to-artifact mapping when paths and stems differ', () => {
    const catalog: CadModelCatalog = {
      version: '3',
      activeModelKey: 'cad-model:models/final-plate',
      models: {
        'cad-model:models/final-plate': {
          contextKey: 'cad-model:models/final-plate',
          modelPath: 'models/final-plate.step',
          sourcePath: 'recipes/plate-generator.py',
          artifacts: [
            { path: 'recipes/plate-generator.py', role: 'source' },
            { path: 'models/final-plate.step', role: 'model' },
          ],
          conversations: {},
          run: { status: 'ready' },
          updatedAt: '2026-08-29T12:00:00.000Z',
        },
      },
    };

    expect(
      resolveCadSourceRebuildModel({
        catalog,
        openedPath: 'models/final-plate.step',
        sourcePath: 'recipes/plate-generator.py',
      }).identity
    ).toEqual({
      contextKey: 'cad-model:models/final-plate',
      modelPath: 'models/final-plate.step',
      sourcePath: 'recipes/plate-generator.py',
    });
  });

  it('uses the opened artifact as the fallback identity before a catalog record exists', () => {
    expect(
      resolveCadSourceRebuildModel({
        catalog: { version: '3', models: {} },
        openedPath: 'parts/bracket.step',
        sourcePath: 'parts/bracket.py',
      }).identity
    ).toEqual({
      contextKey: 'cad-model:parts/bracket',
      modelPath: 'parts/bracket.step',
      sourcePath: 'parts/bracket.py',
    });
  });
});

describe('CAD source rebuild recovery', () => {
  it('restores a source-only backup after a failed first build', () => {
    const snapshot = {
      modelPath: 'parts/bracket.step',
      sourcePath: 'parts/bracket.py',
      sourceBackupPath: '.hardcore/last-good/bracket.source.py',
      recordedAt: '2026-08-29T12:00:00.000Z',
      validationStatus: 'unknown' as const,
    };

    expect(cadSourceRunHasRestorableFiles(snapshot, true)).toBe(true);
    expect(cadSourceRunHasRestorableFiles(snapshot, false)).toBe(false);
  });

  it('always restores an available model backup', () => {
    expect(
      cadSourceRunHasRestorableFiles(
        {
          modelPath: 'parts/bracket.step',
          backupPath: '.hardcore/last-good/bracket.step',
          recordedAt: '2026-08-29T12:00:00.000Z',
          validationStatus: 'unknown',
        },
        false
      )
    ).toBe(true);
  });
});
