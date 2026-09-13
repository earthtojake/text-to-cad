import { UpdateStore } from '@core/features/updates/browser/update-store';
import {
  contributeScopedStore,
  getAppStores,
  scopedStoreToken,
  type AppScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';

const updateStoreToken = scopedStoreToken<UpdateStore>('updates.store');

export const updateAppStoreContributions: readonly AppScopedStoreContribution[] = [
  contributeScopedStore({
    token: updateStoreToken,
    create: () => new UpdateStore(),
    activate: (store) => store.start(),
  }),
];

/** Returns the app-scoped UpdateStore. */
export function getUpdateStore(): UpdateStore {
  return getAppStores().get(updateStoreToken);
}
