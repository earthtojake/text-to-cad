export interface ModalCatalogEntry {
  readonly id: string;
}

export interface ModalCatalog<TDefs extends readonly ModalCatalogEntry[]> {
  readonly defs: TDefs;
  byId(id: string): TDefs[number] | undefined;
}

export type AnyModalCatalog = ModalCatalog<readonly ModalCatalogEntry[]>;

export function defineModalCatalog<const TDefs extends readonly ModalCatalogEntry[]>(
  definitions: TDefs
): ModalCatalog<TDefs> {
  const byId = new Map<string, TDefs[number]>();
  for (const definition of definitions) {
    if (byId.has(definition.id)) {
      throw new Error(`Duplicate modal id: ${definition.id}`);
    }
    byId.set(definition.id, definition);
  }

  const defs = Object.freeze([...definitions]) as unknown as TDefs;
  return Object.freeze({
    defs,
    byId: (id: string) => byId.get(id),
  });
}

export type ModalById<TCatalog extends AnyModalCatalog> = {
  [TDef in TCatalog['defs'][number] as TDef['id']]: TDef;
};

export type ModalIdOf<TCatalog extends AnyModalCatalog> = keyof ModalById<TCatalog> & string;
