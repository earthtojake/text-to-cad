import type { z } from 'zod';
import type { JsonValue } from '@core/primitives/json/api';
import type { Subject } from '@core/primitives/subjects/api';
import type { ViewRef } from '@core/primitives/views/api';

/**
 * Structural slice of a view definition's location contract. The `never`
 * parameter keeps concrete, narrowly-typed contracts assignable; callers pass
 * values validated by `schema` with an `as never` cast.
 */
export interface NavigationLocationContract {
  readonly schema: z.ZodType<JsonValue>;
  readonly key: (location: never) => string;
}

/** Structural slice of a view definition the navigation store needs. */
export interface NavigationViewEntry {
  readonly id: string;
  readonly subject?: ((params: never) => Subject) | undefined;
  readonly location?: NavigationLocationContract | undefined;
  safeRef(params: unknown): ViewRef | undefined;
}

export interface NavigationViewCatalog {
  byId(id: string): NavigationViewEntry | undefined;
}

/**
 * Host-provided navigation environment. The view catalog and the well-known
 * home/settings refs live in feature contributions aggregated by the
 * manifests, so the host bootstrap injects them here instead of this
 * primitive importing feature modules.
 */
export interface NavigationHost {
  readonly views: NavigationViewCatalog;
  readonly homeRef: () => ViewRef;
  readonly settingsViewId: string;
  readonly settingsRef: () => ViewRef;
  /** Reports non-fatal navigation failures to the host log. */
  readonly onError: (message: string, error: unknown) => void;
}

let host: NavigationHost | null = null;

/**
 * Host bootstrap (renderer main.tsx) calls this exactly once, before the app
 * scope builds the navigation stores. Tests call it after resetNavigationHost().
 */
export function seedNavigationHost(next: NavigationHost): void {
  if (host) {
    throw new Error(
      'seedNavigationHost: already seeded. Tests must call resetNavigationHost() first; ' +
        'production seeds exactly once at bootstrap.'
    );
  }
  host = next;
}

export function getNavigationHost(): NavigationHost {
  if (!host) {
    throw new Error(
      'getNavigationHost: no host seeded. The host bootstrap (renderer main.tsx) must call ' +
        'seedNavigationHost() before the navigation stores are created.'
    );
  }
  return host;
}

/** Tests and HMR only: the seeding module registers import.meta.hot?.dispose(resetNavigationHost). */
export function resetNavigationHost(): void {
  host = null;
}
