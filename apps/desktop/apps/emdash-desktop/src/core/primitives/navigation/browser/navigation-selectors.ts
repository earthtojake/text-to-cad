import { getAppStores } from '@core/primitives/scoped-stores/browser';
import { navigationHistoryStoreToken, navigationStoreToken } from './app-stores';
import type { NavigationHistoryStore } from './navigation-history-store';
import type { NavigationStore } from './navigation-store';

/** Returns the app-scoped NavigationStore. */
export function getNavigation(): NavigationStore {
  return getAppStores().get(navigationStoreToken);
}

/** Returns the app-scoped NavigationHistoryStore. */
export function getNavigationHistory(): NavigationHistoryStore {
  return getAppStores().get(navigationHistoryStoreToken);
}
