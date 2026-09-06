import {
  startCadSourceRun,
  type CadLastGoodSnapshot,
  type CadModelIdentity,
} from '@core/features/cad/api/cad-model-state';
import type { CadModelCatalog } from '@core/features/cad/contributions/mementos';
import type { MementoSetter } from '@core/primitives/mementos/react/use-memento';

export function acquireCadSourceRunLease(
  updateCatalog: MementoSetter<CadModelCatalog>,
  identity: CadModelIdentity,
  run: {
    id: string;
    startedAt: string;
    lastGood?: CadLastGoodSnapshot;
  }
): boolean {
  let acquired = false;
  // Memento functional updates run synchronously against the latest value, so
  // checking and installing the source run is one indivisible catalog update.
  updateCatalog((current) => {
    const next = startCadSourceRun(current, identity, run);
    acquired = next !== current;
    return next;
  });
  return acquired;
}
