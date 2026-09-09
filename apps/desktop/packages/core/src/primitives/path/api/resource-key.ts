import { hostRefKey } from '#primitives/host/api';
import { resolveScopedPath } from './resource';
import { comparisonKeyForAbsolutePath, createPathProfile } from './semantics';
import type { HostFileRef, ResourceKey, ResourceKeyOptions, ScopedPath } from './types';

const RESOURCE_KEY_VERSION = 'v1';

export function resourceKeyFromFileRef(
  ref: HostFileRef,
  options: ResourceKeyOptions = {}
): ResourceKey {
  const profile = createPathProfile(options.profile);
  const pathKey = comparisonKeyForAbsolutePath(ref.path, profile);
  return `${RESOURCE_KEY_VERSION}\0${hostRefKey(ref.host)}\0${pathKey}` as ResourceKey;
}

export function resourceKeyFromScopedPath(
  scoped: ScopedPath,
  options: ResourceKeyOptions = {}
): ResourceKey | null {
  const resolved = resolveScopedPath(scoped);
  if (!resolved.success) return null;
  return resourceKeyFromFileRef(resolved.data, options);
}

export function resourceKeyEquals(a: ResourceKey, b: ResourceKey): boolean {
  return a === b;
}

export function compareResourceKeys(a: ResourceKey, b: ResourceKey): -1 | 0 | 1 {
  if (a === b) return 0;
  return a < b ? -1 : 1;
}
