import type { MementoRetention } from './define-memento';

export interface MementoCatalogEntry {
  readonly id: string;
  readonly subject: { readonly kind: string };
  readonly retention: MementoRetention;
}

export function persistedMementosForSubjectKind(
  catalog: readonly MementoCatalogEntry[],
  kind: string
): readonly MementoCatalogEntry[] {
  return catalog.filter(
    (definition) => definition.retention.tier === 'persisted' && definition.subject.kind === kind
  );
}
