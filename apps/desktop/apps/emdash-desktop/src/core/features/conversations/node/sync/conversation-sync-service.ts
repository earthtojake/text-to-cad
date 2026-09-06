import { hostRefKey, isLocalHostRef, type HostRef } from '@emdash/core/primitives/host/api';
import {
  conversationRecordsSchema,
  conversationsContract,
} from '@emdash/core/runtimes/conversations/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { observe, remote, whenReady } from '@emdash/wire/state';
import type { AppDb } from '@core/services/app-db/node/db';
import {
  applyConversationSnapshot,
  type ConversationHostIdentity,
} from './apply-conversation-snapshot';

export interface ConversationSyncServiceOptions {
  db: AppDb;
  runtimes: RuntimeBroker;
  scope?: Scope;
  onError?: (context: string, error: unknown) => void;
}

/**
 * Converges the client conversation registry toward each reachable host's index by
 * subscribing to that host's `records` live model (spec §5.3). The replica delivers the
 * authoritative initial state and re-delivers the full map on every host diff, and every
 * delivery routes through the same idempotent snapshot transaction — diffs are never
 * load-bearing on their own, since a reconnect replays full initial state.
 *
 * Reachability is positive-assertion: an unresolvable host client attaches nothing and
 * sweeps nothing; cached rows keep serving reads until the host comes back.
 */
export class ConversationSyncService {
  private readonly attachments = new Map<string, Scope>();
  private disposed = false;

  constructor(private readonly options: ConversationSyncServiceOptions) {
    options.scope?.add(() => this.dispose());
  }

  async attachHost(host: HostRef): Promise<void> {
    if (this.disposed) return;
    this.detachHost(host);
    const client = await this.options.runtimes.client(host);
    if (!client.success) return;
    const key = hostRefKey(host);
    if (this.disposed || this.attachments.has(key)) return;

    const scope = createScope({ label: `conversation-sync:${key}` });
    this.attachments.set(key, scope);
    const records = remote(conversationsContract.records, client.data.conversations.records, {
      scope,
    });
    const list = records(undefined).states.list;
    const hostIdentity = hostIdentityFor(host);
    let chain = Promise.resolve();
    observe(
      list,
      (snapshot) => {
        if (snapshot.status === 'loading') return;
        const parsed = conversationRecordsSchema.parse(snapshot.value ?? {});
        chain = chain
          .then(async () => {
            await applyConversationSnapshot({
              db: this.options.db,
              host: hostIdentity,
              records: parsed,
            });
          })
          .catch((error) => {
            this.options.onError?.('conversation snapshot sync', error);
          });
      },
      { scope }
    );
    await whenReady(list, { scope });
    await chain;
    if (this.attachments.get(key) !== scope) await scope.dispose();
  }

  detachHost(host: HostRef): void {
    const scope = this.attachments.get(hostRefKey(host));
    if (!scope) return;
    this.attachments.delete(hostRefKey(host));
    void scope.dispose();
  }

  dispose(): void {
    this.disposed = true;
    for (const scope of this.attachments.values()) {
      void scope.dispose();
    }
    this.attachments.clear();
  }
}

function hostIdentityFor(host: HostRef): ConversationHostIdentity {
  return isLocalHostRef(host)
    ? { location: 'local', sshConnectionId: null }
    : { location: 'remote', sshConnectionId: host.id };
}
