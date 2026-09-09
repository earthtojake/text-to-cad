import type { PaletteProviderDef } from './provider';

export interface PaletteProviderCatalog<TProviders extends readonly PaletteProviderDef[]> {
  readonly providers: TProviders;
  byKind(kind: string): TProviders[number] | undefined;
  byKeyword(keyword: string): TProviders[number] | undefined;
}

export function definePaletteProviderCatalog<
  const TProviders extends readonly PaletteProviderDef[],
>(providers: TProviders): PaletteProviderCatalog<TProviders> {
  const byKind = new Map<string, TProviders[number]>();
  const byKeyword = new Map<string, TProviders[number]>();

  for (const provider of providers) {
    if (byKind.has(provider.kind)) {
      throw new Error(`Duplicate palette provider kind: ${provider.kind}`);
    }
    if (byKeyword.has(provider.keyword)) {
      throw new Error(`Duplicate palette provider keyword: ${provider.keyword}`);
    }
    byKind.set(provider.kind, provider);
    byKeyword.set(provider.keyword, provider);
  }

  const definitions = Object.freeze([...providers]) as unknown as TProviders;
  return Object.freeze({
    providers: definitions,
    byKind: (kind: string) => byKind.get(kind),
    byKeyword: (keyword: string) => byKeyword.get(keyword),
  });
}
