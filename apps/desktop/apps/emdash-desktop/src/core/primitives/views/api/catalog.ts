import type { JsonObject } from '@core/primitives/json/api';
import type { ViewRef } from './define-view';

export interface ViewCatalogEntry {
  readonly id: string;
  safeRef(params: unknown): ViewRef<string, JsonObject> | undefined;
}

export interface ViewCatalog<TDefs extends readonly ViewCatalogEntry[]> {
  readonly defs: TDefs;
  byId(id: string): TDefs[number] | undefined;
}

export function defineViewCatalog<const TDefs extends readonly ViewCatalogEntry[]>(
  definitions: TDefs
): ViewCatalog<TDefs> {
  const byId = new Map<string, TDefs[number]>();
  for (const definition of definitions) {
    if (byId.has(definition.id)) {
      throw new Error(`Duplicate view id: ${definition.id}`);
    }
    byId.set(definition.id, definition);
  }

  const defs = Object.freeze([...definitions]) as unknown as TDefs;
  return Object.freeze({
    defs,
    byId: (id: string) => byId.get(id),
  });
}
