import { cadModelContextKey } from '@core/features/cad/api/browser/cad-agent';
import type { CadLastGoodSnapshot, CadModelIdentity } from '@core/features/cad/api/cad-model-state';
import type { CadModelCatalog, CadModelRecord } from '@core/features/cad/contributions/mementos';
import { cadOutputPath } from './cad-design-history-model';

export function resolveCadSourceRebuildModel(input: {
  catalog: CadModelCatalog;
  openedPath: string;
  sourcePath: string;
}): { identity: CadModelIdentity; model?: CadModelRecord } {
  const openedModelPath = cadOutputPath(input.openedPath);
  const openedContextKey = cadModelContextKey(openedModelPath);
  const openedModel = input.catalog.models[openedContextKey];
  const sourceMatches = Object.values(input.catalog.models).filter(
    (model) => model.sourcePath && samePath(model.sourcePath, input.sourcePath)
  );
  const model = openedModel ?? (sourceMatches.length === 1 ? sourceMatches[0] : undefined);

  return {
    identity: model
      ? {
          contextKey: model.contextKey,
          modelPath: model.modelPath,
          sourcePath: model.sourcePath ?? input.sourcePath,
        }
      : {
          contextKey: openedContextKey,
          modelPath: openedModelPath,
          sourcePath: input.sourcePath,
        },
    ...(model ? { model } : {}),
  };
}

export function cadSourceRunHasRestorableFiles(
  snapshot: CadLastGoodSnapshot | undefined,
  restoreSourceOnFailure: boolean
): snapshot is CadLastGoodSnapshot {
  return Boolean(
    snapshot?.backupPath ||
    (restoreSourceOnFailure && snapshot?.sourcePath && snapshot.sourceBackupPath)
  );
}

function samePath(left: string, right: string): boolean {
  return normalizePath(left) === normalizePath(right);
}

function normalizePath(path: string): string {
  return path.replaceAll('\\', '/').replace(/^\.\//, '');
}
