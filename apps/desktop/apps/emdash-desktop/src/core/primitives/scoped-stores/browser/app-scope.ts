import {
  ScopedStoreHost,
  type ScopedStoreContribution,
  type ScopedStoreLookup,
} from './scoped-store-host';

/**
 * Context passed to app-scoped store contributions. The app scope is a
 * singleton with no per-instance data, so the context is intentionally empty.
 */
export type AppScopedStoreContext = Readonly<Record<string, never>>;

export type AppScopedStoreContribution = ScopedStoreContribution<AppScopedStoreContext>;

let appScopeHost: ScopedStoreHost<AppScopedStoreContext> | undefined;

/**
 * Builds the app-level ScopedStoreHost from the given contributions and
 * activates it synchronously. The renderer bootstrap passes the aggregated
 * manifest contributions so this primitive never imports feature manifests.
 */
export function createAppScope(contributions: readonly AppScopedStoreContribution[]): void {
  if (appScopeHost) {
    throw new Error(
      'createAppScope was called twice. The app scope must be created exactly once during ' +
        'renderer bootstrap; call resetAppScope() first if you need to rebuild it in tests or HMR.'
    );
  }
  const host = new ScopedStoreHost<AppScopedStoreContext>({}, contributions);
  host.activate();
  appScopeHost = host;
}

/** Lookup for app-scoped stores. Selectors in owning slices are the public access path. */
export function getAppStores(): ScopedStoreLookup {
  if (!appScopeHost) {
    throw new Error(
      'createAppScope must run in renderer bootstrap before React mounts; an app store was ' +
        'accessed before the app scope was created.'
    );
  }
  return appScopeHost;
}

/** Disposes the app scope and clears the singleton. For tests and HMR only. */
export function resetAppScope(): void {
  appScopeHost?.dispose();
  appScopeHost = undefined;
}
