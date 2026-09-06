import { isDeepEqual } from '@emdash/shared';
import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { cell, expose, peek, produce, type Cell } from '@emdash/wire/state';
import { hostsContract, type HostServerRuntime, type HostServerState } from '../api';

export class HostStateModel {
  readonly runtime: Cell<HostServerRuntime>;
  readonly host: LeasedLiveModelProvider<typeof hostsContract.serverStates>;

  constructor() {
    this.runtime = cell<HostServerRuntime>({});
    this.host = expose(hostsContract.serverStates, { runtime: this.runtime });
  }

  set(connectionId: string, state: HostServerState): void {
    this.runtime.set(
      produce(peek(this.runtime), (runtime) => {
        // Assigning a fresh deep-equal object would still produce a patch; skip
        // the write so identical states never emit updates to subscribers.
        if (isDeepEqual(runtime[connectionId], state)) return;
        runtime[connectionId] = state;
      })
    );
  }

  get(connectionId: string): HostServerState | undefined {
    return peek(this.runtime)[connectionId];
  }

  remove(connectionId: string): void {
    this.runtime.set(
      produce(peek(this.runtime), (runtime) => {
        delete runtime[connectionId];
      })
    );
  }

  markConnectionLost(connectionId: string): void {
    this.runtime.set(
      produce(peek(this.runtime), (runtime) => {
        const current = runtime[connectionId];
        if (current?.status !== 'healthy') return;
        runtime[connectionId] = {
          status: 'stopped',
          version: current.version,
          latestVersion: current.latestVersion,
          updateAvailable: current.updateAvailable,
        };
      })
    );
  }

  snapshot(): HostServerRuntime {
    return peek(this.runtime);
  }

  dispose(): void {
    void this.host.dispose();
  }
}
