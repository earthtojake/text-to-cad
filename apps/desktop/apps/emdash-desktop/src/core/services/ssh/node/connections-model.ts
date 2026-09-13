import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { cell, expose, peek, produce, type Cell } from '@emdash/wire/state';
import type { ConnectionState, SshConnectionEvent } from '@core/primitives/ssh/api';
import { sshContract, type SshConnectionsRuntime } from '../api';

export class SshConnectionsModel {
  readonly runtime: Cell<SshConnectionsRuntime>;
  readonly host: LeasedLiveModelProvider<typeof sshContract.connections>;

  constructor() {
    this.runtime = cell<SshConnectionsRuntime>({});
    this.host = expose(sshContract.connections, { runtime: this.runtime });
  }

  publishEvent(event: SshConnectionEvent): void {
    this.runtime.set(
      produce(peek(this.runtime), (runtime) => {
        if (event.type === 'health-changed') {
          runtime[event.connectionId] = {
            state: runtime[event.connectionId]?.state ?? 'disconnected',
            health: event.health,
          };
          return;
        }

        setState(runtime, event.connectionId, stateForEvent(event));
      })
    );
  }

  remove(connectionId: string): void {
    this.runtime.set(
      produce(peek(this.runtime), (runtime) => {
        delete runtime[connectionId];
      })
    );
  }

  snapshot(): SshConnectionsRuntime {
    return peek(this.runtime);
  }

  dispose(): void {
    void this.host.dispose();
  }
}

function setState(
  runtime: SshConnectionsRuntime,
  connectionId: string,
  state: ConnectionState
): void {
  runtime[connectionId] = {
    state,
    health: runtime[connectionId]?.health ?? { status: 'ok' },
  };
}

function stateForEvent(
  event: Exclude<SshConnectionEvent, { type: 'health-changed' }>
): ConnectionState {
  switch (event.type) {
    case 'connected':
    case 'reconnected':
      return 'connected';
    case 'connecting':
      return 'connecting';
    case 'reconnecting':
      return 'reconnecting';
    case 'disconnected':
    case 'reconnect-failed':
      return 'disconnected';
    case 'error':
      return 'error';
  }
}
