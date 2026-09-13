import { MachinesStore } from '@core/features/machines/browser/machines-store';
import {
  contributeScopedStore,
  getAppStores,
  scopedStoreToken,
  type AppScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';

const machinesStoreToken = scopedStoreToken<MachinesStore>('machines.store');

export const machinesAppStoreContributions: readonly AppScopedStoreContribution[] = [
  contributeScopedStore({
    token: machinesStoreToken,
    create: () => new MachinesStore(),
    activate: (store) => void store.start(),
    dispose: (store) => store.dispose(),
  }),
];

/** Returns the app-scoped MachinesStore. */
export function getMachinesStore(): MachinesStore {
  return getAppStores().get(machinesStoreToken);
}
