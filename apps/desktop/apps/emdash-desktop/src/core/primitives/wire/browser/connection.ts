import {
  client,
  defineContract,
  type Connection,
  type ContractDefinitions,
} from '@emdash/wire/rpc';

type WireConnectionSource = () => Promise<Connection>;

let source: WireConnectionSource | null = null;
let cached: Promise<Connection> | null = null;
const domainClients = new Map<string, Promise<unknown>>();

/**
 * Host bootstrap (renderer main.tsx) calls this exactly once, before React mounts.
 * Tests call it after resetWireConnection() with an in-process connection.
 * Lazy: the thunk runs on first getWireConnection() call, not at seed time.
 */
export function seedWireConnection(next: WireConnectionSource): void {
  if (source) {
    throw new Error(
      'seedWireConnection: already seeded. Tests must call resetWireConnection() first; ' +
        'production seeds exactly once at bootstrap.'
    );
  }
  source = next;
}

export function getWireConnection(): Promise<Connection> {
  if (!source) {
    throw new Error(
      'getWireConnection: no connection seeded. The host bootstrap (renderer main.tsx) must ' +
        'call seedWireConnection() before any wire access.'
    );
  }
  cached ??= source();
  return cached;
}

/** Tests and HMR only: the seeding module registers import.meta.hot?.dispose(resetWireConnection). */
export function resetWireConnection(): void {
  source = null;
  cached = null;
  domainClients.clear();
}

/**
 * The wire entry point feature clients use. `contract` is the slice's own contract;
 * `domain` is the slice's exported domain constant (single-sourced into the manifests).
 * Routes identically to the aggregate client: the slice contract is re-nested under
 * its domain key so every endpoint kind carries the `${domain}.` prefix — call paths
 * AND live topics (a bare `pathPrefix` would prefix only call paths, leaving live
 * model/log/job topics unroutable through the desktop routing controller).
 */
export function domainClient<C>(domain: string, contract: ContractDefinitions): Promise<C> {
  let entry = domainClients.get(domain);
  if (!entry) {
    entry = getWireConnection().then((connection) => {
      // oxlint-disable-next-line typescript/no-explicit-any -- generic seam over any slice contract
      const nested = defineContract({ [domain]: contract } as any) as Record<string, unknown>;
      // oxlint-disable-next-line typescript/no-explicit-any -- generic seam over any slice contract
      return (client(nested as any, connection) as Record<string, unknown>)[domain] as C;
    });
    domainClients.set(domain, entry);
  }
  return entry as Promise<C>;
}
