import type { ResourceUri } from '@emdash/core/primitives/path/api';
import type { GitRef } from '@core/primitives/git/api';
import { gitRefToString } from '@core/primitives/git/api';

/**
 * One of the facets of a single open file (spec §6/§7): the writable buffer,
 * the read-only disk mirror, and read-only git snapshots — one per ref, so an
 * entry can hold several git facets at once (e.g. both sides of a merge-base
 * diff).
 */
export type Facet = { kind: 'buffer' } | { kind: 'disk' } | { kind: 'git'; ref: GitRef };

/**
 * The small editor-framework-free interface each facet exposes to
 * OpenFileStore — the store's only view of facet content. All editing policy
 * (dirty, etag, conflict, save) is computed against this interface, never
 * against Monaco types. Ticket 06 provides the `MonacoFacetBinder`
 * implementation over ITextModel; tests use fakes.
 */
export interface FacetHandle {
  /** Current full text of the facet. */
  getText(): string;
  /**
   * Replace the full text, preserving undo history and cursor position where
   * the implementation can (e.g. Monaco applies a full-range edit rather than
   * resetting the model). Change events for this edit must be delivered
   * synchronously before `setText` returns, so the store can distinguish its
   * own programmatic writes from user edits.
   */
  setText(text: string): void;
  /** Subscribe to text changes. Returns an unsubscribe function. */
  onDidChange(listener: () => void): () => void;
  dispose(): void;
}

/**
 * Everything a binder needs to materialize a facet handle. The URI is the
 * entry's current spelling — re-keyed entries get fresh descriptors, so a
 * binder can derive its editor-side URIs deterministically from
 * `uri` + `facet` (the facet URI codec, spec §7).
 */
export type FacetDescriptor = Readonly<{
  uri: ResourceUri;
  facet: Facet;
  /** Text the handle must start with (disk content, or the buffer seed). */
  initialText: string;
  /** True for disk-mirror and git-snapshot facets; false for the buffer. */
  readonly: boolean;
}>;

/**
 * The seam through which OpenFileStore obtains facet handles. Registered once
 * at startup by the editor bootstrap (ticket 06 supplies the Monaco-backed
 * implementation). A rejected `createHandle` degrades the entry to an error
 * placeholder instead of wedging the stack (spec §7).
 */
export interface FacetHandleBinder {
  createHandle(descriptor: FacetDescriptor): FacetHandle | Promise<FacetHandle>;
}

/**
 * Stable identity of a facet within one entry. Git facets are parameterized
 * by ref, so each acquired ref owns its own slot.
 */
export function facetSlotKey(facet: Facet): string {
  switch (facet.kind) {
    case 'buffer':
      return 'buffer';
    case 'disk':
      return 'disk';
    case 'git':
      return `git:${facet.ref.kind}:${gitRefToString(facet.ref)}`;
  }
}
