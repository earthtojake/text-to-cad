import { projectManagerStoreToken } from '@core/features/projects/contributions/app-store-tokens';
import { SidebarStore } from '@core/features/workbench/browser/sidebar/sidebar-store';
import {
  contributeScopedStore,
  getAppStores,
  scopedStoreToken,
  type AppScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';

const sidebarStoreToken = scopedStoreToken<SidebarStore>('workbench.sidebar');

// SidebarStore resolves the projects store at create time, so the projects
// contribution must be registered before this one in the app-scope manifest.
export const workbenchAppStoreContributions: readonly AppScopedStoreContribution[] = [
  contributeScopedStore({
    token: sidebarStoreToken,
    create: (_context, stores) => new SidebarStore(stores.get(projectManagerStoreToken)),
  }),
];

/** Returns the app-scoped SidebarStore. */
export function getSidebarStore(): SidebarStore {
  return getAppStores().get(sidebarStoreToken);
}
