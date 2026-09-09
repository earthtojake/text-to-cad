import type { OpenTarget, TabProvider, TabResource } from './tab-provider';

// ── Type aliases ──────────────────────────────────────────────────────────────

// oxlint-disable-next-line typescript/no-explicit-any
export type AnyTabProvider = TabProvider<any, any, any, any>;

/**
 * Extract the literal kind union from a typed registry.
 */
export type KindOf<R extends TabRegistry> =
  R extends TypedTabRegistry<infer P> ? P[number]['kind'] : string;

/**
 * Extract the OpenArgs type for a given kind from a typed registry.
 */
export type OpenArgsOf<R extends TabRegistry, K extends KindOf<R>> =
  R extends TypedTabRegistry<infer P>
    ? Extract<P[number], { kind: K }> extends TabProvider<K, infer _S, infer _T, infer A>
      ? A
      : unknown
    : unknown;

/**
 * Extract the resource type (T) for a given kind from a typed registry.
 */
export type ResourceOf<R extends TabRegistry, K extends KindOf<R>> =
  R extends TypedTabRegistry<infer P>
    ? Extract<P[number], { kind: K }> extends TabProvider<K, infer _S, infer T, infer _A>
      ? T
      : TabResource
    : TabResource;

/**
 * Strongly-typed discriminated union of all open-arg shapes in a registry.
 * Used by the public layout-level open() entry point.
 *
 * Each member is { kind: K } & OpenArgsOf<R, K>, so callers get
 * exhaustive completions and type errors for unknown kinds.
 */
export type TabOpenArgs<R extends TabRegistry> = {
  [K in KindOf<R>]: { kind: K } & OpenArgsOf<R, K>;
}[KindOf<R>];

/**
 * Control flags that may accompany any TabOpenArgs call.
 * Stripped before the args reach onBeforeOpen.
 */
export interface TabOpenOptions {
  /** When true, opens as a preview tab (replaced on next preview open). */
  preview?: boolean;
  /**
   * When true and the tab is already open (single-mount hit), replace its
   * current state with the new open args. Ignored for multi-mount providers.
   */
  overrideState?: boolean;
  /**
   * Which pane to open into. Defaults to 'active' (focused pane).
   * 'right'/'left' will split if needed; { paneId } targets an explicit pane.
   */
  target?: OpenTarget;
}

// ── Registry interface ────────────────────────────────────────────────────────

/**
 * Immutable registry of tab providers, constructed via createTabRegistry.
 * Each PaneStore holds a reference; React chrome reads it off the store
 * through PaneContext so no extra React context is needed.
 */
export interface TabRegistry {
  get(kind: string): AnyTabProvider;
  all(): AnyTabProvider[];
  has(kind: string): boolean;
}

/** Typed registry that retains the full provider tuple for type inference. */
export interface TypedTabRegistry<P extends readonly AnyTabProvider[]> extends TabRegistry {
  /** @internal Used for type-level inference only; do not call at runtime. */
  readonly _providers: P;
}

// ── Factories ─────────────────────────────────────────────────────────────────

/**
 * Identity helper that captures the generic parameters so providers
 * can be authored as plain object literals without losing type inference.
 *
 * ```ts
 * export const myTabProvider = createTabProvider({
 *   kind: 'my-kind',
 *   mount: { type: 'single', dedupKey: (s) => s.id },
 *   initialize: (entry, handle, ctx) => { ... },
 *   dispose: (entry, resource, ctx) => { ... },
 *   ...
 * });
 * ```
 */
export function createTabProvider<K extends string, S, T extends TabResource, OpenArgs = S>(
  impl: TabProvider<K, S, T, OpenArgs>
): TabProvider<K, S, T, OpenArgs> {
  return impl;
}

/**
 * Builds an immutable TypedTabRegistry from a const tuple of providers.
 * Call once per view that needs a tab surface (e.g. in task-tab-registry.ts).
 */
export function createTabRegistry<const P extends readonly AnyTabProvider[]>(
  providers: P
): TypedTabRegistry<P> {
  const map = new Map<string, AnyTabProvider>();
  for (const p of providers) {
    map.set(p.kind, p);
  }
  const registry: TypedTabRegistry<P> = {
    get(kind: string): AnyTabProvider {
      const def = map.get(kind);
      if (!def) throw new Error(`No tab provider registered for kind: ${kind}`);
      return def;
    },
    all(): AnyTabProvider[] {
      return [...map.values()];
    },
    has(kind: string): boolean {
      return map.has(kind);
    },
    // oxlint-disable-next-line typescript/no-explicit-any
    _providers: providers as any,
  };
  return registry;
}
