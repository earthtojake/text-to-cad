import { log } from '@emdash/shared/logger';
import type {
  PaletteContext,
  PaletteMatchBand,
  PaletteProviderDef,
  PaletteProviderMatch,
} from './provider';
import type { PaletteProviderCatalog } from './provider-catalog';

const PROVIDER_RESULT_LIMIT = 12;
const TOTAL_RESULT_LIMIT = 20;

const BAND_ORDER: Record<PaletteMatchBand, number> = {
  exact: 0,
  prefix: 1,
  substring: 2,
  fuzzy: 3,
  secondary: 4,
};

export interface PaletteResult {
  readonly identity: string;
  readonly provider: PaletteProviderDef;
  readonly match: PaletteProviderMatch;
}

export interface PaletteControllerSnapshot {
  readonly input: string;
  readonly query: string;
  readonly mode?: {
    readonly kind: PaletteProviderDef['kind'];
    readonly keyword: PaletteProviderDef['keyword'];
  };
  readonly results: readonly PaletteResult[];
  readonly selectedIdentity?: string;
  readonly pending: boolean;
}

interface RankedResult extends PaletteResult {
  readonly providerOrder: number;
  readonly itemOrder: number;
}

const EMPTY_SNAPSHOT: PaletteControllerSnapshot = {
  input: '',
  query: '',
  results: [],
  pending: false,
};

export class PaletteController {
  private generation = 0;
  private snapshot: PaletteControllerSnapshot = EMPTY_SNAPSHOT;
  private readonly listeners = new Set<() => void>();

  constructor(private readonly catalog: PaletteProviderCatalog<readonly PaletteProviderDef[]>) {}

  getSnapshot(): PaletteControllerSnapshot {
    return this.snapshot;
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  select(identity: string): void {
    if (!this.snapshot.results.some((result) => result.identity === identity)) return;
    if (this.snapshot.selectedIdentity === identity) return;
    this.snapshot = { ...this.snapshot, selectedIdentity: identity };
    this.emit();
  }

  setInput(input: string, context: PaletteContext, delayMs = 0): Promise<void> {
    const generation = ++this.generation;
    const parsed = parseInput(input, this.catalog);
    const { query, mode } = parsed;
    const providers = mode ? [mode.provider] : this.catalog.providers;
    this.snapshot = {
      input,
      query,
      mode: mode ? { kind: mode.provider.kind, keyword: mode.provider.keyword } : undefined,
      results: [],
      selectedIdentity: undefined,
      pending: delayMs > 0,
    };
    this.emit();

    const run = (): Promise<void> => {
      if (generation !== this.generation) return Promise.resolve();
      const providerResults = new Map<PaletteProviderDef, readonly PaletteProviderMatch[]>();
      const pending: Promise<void>[] = [];

      for (const provider of providers) {
        const source =
          query.length === 0
            ? (provider.idle?.(context) ?? [])
            : query.length < provider.minQueryLength
              ? []
              : provider.search({ query, context });
        if (isPromise(source)) {
          pending.push(
            Promise.resolve(source)
              .then((matches) => {
                if (generation !== this.generation) return;
                providerResults.set(provider, matches);
                this.publish(input, query, mode?.provider, providerResults, true);
              })
              .catch((error: unknown) => {
                if (generation !== this.generation) return;
                log.warn('PaletteController: provider query failed', {
                  provider: provider.kind,
                  query,
                  error: String(error),
                });
                providerResults.set(provider, []);
                this.publish(input, query, mode?.provider, providerResults, true);
              })
          );
        } else {
          providerResults.set(provider, source);
        }
      }

      this.publish(input, query, mode?.provider, providerResults, pending.length > 0);
      return Promise.all(pending).then(() => {
        if (generation !== this.generation) return;
        this.publish(input, query, mode?.provider, providerResults, false);
      });
    };

    if (delayMs <= 0) return run();
    return new Promise((resolve) => {
      setTimeout(() => void run().then(resolve), delayMs);
    });
  }

  private publish(
    input: string,
    query: string,
    mode: PaletteProviderDef | undefined,
    providerResults: ReadonlyMap<PaletteProviderDef, readonly PaletteProviderMatch[]>,
    pending: boolean
  ): void {
    const ranked = [...providerResults].flatMap(([provider, matches]) =>
      matches
        .map(
          (match, itemOrder): RankedResult => ({
            identity: `${provider.kind}:${match.id}`,
            provider,
            match,
            providerOrder: this.catalog.providers.indexOf(provider),
            itemOrder,
          })
        )
        .sort(compareResults)
        .slice(0, mode ? TOTAL_RESULT_LIMIT : PROVIDER_RESULT_LIMIT)
    );
    const results = ranked
      .sort(compareResults)
      .slice(0, TOTAL_RESULT_LIMIT)
      .map(({ identity, provider, match }) => ({ identity, provider, match }));
    const selectedIdentity = results.some(
      ({ identity }) => identity === this.snapshot.selectedIdentity
    )
      ? this.snapshot.selectedIdentity
      : results[0]?.identity;

    this.snapshot = {
      input,
      query,
      mode: mode ? { kind: mode.kind, keyword: mode.keyword } : undefined,
      results,
      selectedIdentity,
      pending,
    };
    this.emit();
  }

  private emit(): void {
    for (const listener of this.listeners) listener();
  }
}

function isPromise<T>(value: T | Promise<T>): value is Promise<T> {
  return typeof (value as Promise<T>).then === 'function';
}

function parseInput(
  input: string,
  catalog: PaletteProviderCatalog<readonly PaletteProviderDef[]>
): {
  query: string;
  mode?: { provider: PaletteProviderDef };
} {
  const trimmed = input.trim();
  const separator = trimmed.search(/\s/);
  const token = separator === -1 ? trimmed : trimmed.slice(0, separator);
  const provider = catalog.byKeyword(token);
  if (!provider) return { query: trimmed };
  return {
    query: separator === -1 ? '' : trimmed.slice(separator).trim(),
    mode: { provider },
  };
}

function compareResults(a: RankedResult, b: RankedResult): number {
  return (
    BAND_ORDER[a.match.relevance.band] - BAND_ORDER[b.match.relevance.band] ||
    b.match.relevance.score - a.match.relevance.score ||
    (b.match.relevance.contextAffinity ?? 0) - (a.match.relevance.contextAffinity ?? 0) ||
    (b.match.relevance.recency ?? 0) - (a.match.relevance.recency ?? 0) ||
    a.providerOrder - b.providerOrder ||
    a.itemOrder - b.itemOrder ||
    a.identity.localeCompare(b.identity)
  );
}
