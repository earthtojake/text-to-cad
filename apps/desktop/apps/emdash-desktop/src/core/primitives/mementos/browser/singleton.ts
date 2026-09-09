import type { MementoCatalogEntry } from '@core/primitives/mementos/api';
import { MementoClient } from './memento-client';

type MementosWireClient = ConstructorParameters<typeof MementoClient>[0];

export interface MementosBootstrapDeps {
  readonly getWireClient: () => Promise<MementosWireClient>;
  readonly catalog: readonly MementoCatalogEntry[];
  readonly onError?: (error: unknown) => void;
}

let deps: MementosBootstrapDeps | undefined;
let client: MementoClient | undefined;
let initializing: Promise<MementoClient> | undefined;

export function configureMementos(nextDeps: MementosBootstrapDeps): void {
  if (client || initializing) {
    throw new Error('Mementos must be configured before initialization');
  }
  deps = nextDeps;
}

export function initMementos(): Promise<MementoClient> {
  if (client) return Promise.resolve(client);
  if (!deps) throw new Error('Mementos have not been configured');
  const configured = deps;
  initializing ??= configured.getWireClient().then((wire) => {
    client = new MementoClient(wire, {
      catalog: configured.catalog,
      onError: configured.onError,
    });
    return client;
  });
  return initializing;
}

export function getMementoClient(): MementoClient {
  if (!client) throw new Error('Mementos have not been initialized');
  return client;
}
