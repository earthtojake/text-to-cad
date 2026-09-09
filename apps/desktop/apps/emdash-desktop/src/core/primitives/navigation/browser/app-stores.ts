import {
  contributeScopedStore,
  scopedStoreToken,
  type AppScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';
import { NavigationHistoryStore } from './navigation-history-store';
import { NavigationStore } from './navigation-store';

export const navigationHistoryStoreToken =
  scopedStoreToken<NavigationHistoryStore>('navigation.history');
export const navigationStoreToken = scopedStoreToken<NavigationStore>('navigation.store');

// The history contribution must be registered before the navigation store,
// which resolves it at create time. Creating the NavigationStore requires the
// navigation host seam to be seeded (seedNavigationHost) beforehand.
export const navigationAppStoreContributions: readonly AppScopedStoreContribution[] = [
  contributeScopedStore({
    token: navigationHistoryStoreToken,
    create: () => new NavigationHistoryStore(),
  }),
  contributeScopedStore({
    token: navigationStoreToken,
    create: (_context, stores) => new NavigationStore(stores.get(navigationHistoryStoreToken)),
    dispose: (store) => store.dispose(),
  }),
];
