export type ScopedStoreToken<T> = Readonly<{
  id: string;
  /** Type-only value marker. */
  __value?: T;
}>;

export type ScopedStoreValue<Token> = Token extends ScopedStoreToken<infer Value> ? Value : never;

export interface ScopedStoreLookup {
  get<Token extends ScopedStoreToken<unknown>>(token: Token): ScopedStoreValue<Token>;
  has(token: ScopedStoreToken<unknown>): boolean;
}

export type ScopedStoreContribution<Context> = Readonly<{
  token: ScopedStoreToken<unknown>;
  create(context: Context, stores: ScopedStoreLookup): unknown;
  ready?(store: unknown, context: Context): PromiseLike<unknown>;
  activate?(store: unknown, context: Context): void;
  dispose?(store: unknown, context: Context): void;
}>;

type TypedScopedStoreContribution<Context, Store> = Readonly<{
  token: ScopedStoreToken<Store>;
  create(context: Context, stores: ScopedStoreLookup): Store;
  ready?(store: Store, context: Context): PromiseLike<unknown>;
  activate?(store: Store, context: Context): void;
  dispose?(store: Store, context: Context): void;
}>;

export function scopedStoreToken<T>(id: string): ScopedStoreToken<T> {
  if (!id) throw new TypeError('Scoped store token id must not be empty');
  return Object.freeze({ id });
}

export function contributeScopedStore<Context, Store>(
  contribution: TypedScopedStoreContribution<Context, Store>
): ScopedStoreContribution<Context> {
  return Object.freeze({
    token: contribution.token as ScopedStoreToken<unknown>,
    create: contribution.create,
    ready: contribution.ready
      ? (store, context) => contribution.ready!(store as Store, context)
      : undefined,
    activate: contribution.activate
      ? (store, context) => contribution.activate!(store as Store, context)
      : undefined,
    dispose: contribution.dispose
      ? (store, context) => contribution.dispose!(store as Store, context)
      : undefined,
  });
}

export class ScopedStoreHost<Context> implements ScopedStoreLookup {
  private readonly stores = new Map<string, unknown>();
  private readonly contributions: readonly ScopedStoreContribution<Context>[];
  private readonly createdContributions: ScopedStoreContribution<Context>[] = [];
  private activated = false;
  private disposed = false;
  private readyPromise: Promise<void> | undefined;

  constructor(
    private readonly context: Context,
    contributions: readonly ScopedStoreContribution<Context>[],
    private readonly disposeOrder: 'forward' | 'reverse' = 'reverse'
  ) {
    this.contributions = [...contributions];
    try {
      for (const contribution of this.contributions) {
        if (this.stores.has(contribution.token.id)) {
          throw new Error(`Duplicate scoped store token '${contribution.token.id}'`);
        }
        this.stores.set(contribution.token.id, contribution.create(context, this));
        this.createdContributions.push(contribution);
      }
    } catch (error) {
      this.dispose();
      throw error;
    }
  }

  get<Token extends ScopedStoreToken<unknown>>(token: Token): ScopedStoreValue<Token> {
    if (!this.stores.has(token.id)) {
      throw new Error(`Scoped store '${token.id}' is not registered`);
    }
    return this.stores.get(token.id) as ScopedStoreValue<Token>;
  }

  has(token: ScopedStoreToken<unknown>): boolean {
    return this.stores.has(token.id);
  }

  ready(): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('ScopedStoreHost is disposed'));
    if (!this.readyPromise) {
      try {
        this.readyPromise = Promise.all(
          this.contributions.map((contribution) =>
            Promise.resolve(
              contribution.ready?.(this.stores.get(contribution.token.id), this.context)
            )
          )
        ).then(() => undefined);
      } catch (error) {
        this.readyPromise = Promise.reject(error);
      }
    }
    return this.readyPromise;
  }

  activate(): void {
    if (this.disposed) throw new Error('ScopedStoreHost is disposed');
    if (this.activated) return;
    this.activated = true;
    for (const contribution of this.contributions) {
      contribution.activate?.(this.stores.get(contribution.token.id), this.context);
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    const contributions =
      this.disposeOrder === 'reverse'
        ? [...this.createdContributions].reverse()
        : this.createdContributions;
    for (const contribution of contributions) {
      contribution.dispose?.(this.stores.get(contribution.token.id), this.context);
    }
    this.stores.clear();
  }
}
