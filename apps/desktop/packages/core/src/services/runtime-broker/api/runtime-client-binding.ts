import type { Unsubscribe } from '@emdash/shared';
import {
  client as createClient,
  WireError,
  type AttachOptions,
  type BlobSource,
  type Connection,
  type LiveSnapshot,
  type LiveUpdate,
} from '@emdash/wire/rpc';
import { hostRuntimesContract } from './contract';
import type { HostRuntimesClient } from './runtime-broker';

export type RuntimeClientSource =
  | HostRuntimesClient
  | Readonly<{
      client: HostRuntimesClient;
      connection: Connection;
    }>;

export interface RuntimeClientBinding {
  readonly client: HostRuntimesClient;
  rebind(source: RuntimeClientSource): boolean;
  dispose(): void;
}

export function createRuntimeClientBinding(source: RuntimeClientSource): RuntimeClientBinding {
  if (isConnectionSource(source)) return new ConnectionRuntimeClientBinding(source.connection);
  return new DirectRuntimeClientBinding(source);
}

function isConnectionSource(
  source: RuntimeClientSource
): source is Extract<RuntimeClientSource, { connection: Connection }> {
  return 'client' in source && 'connection' in source;
}

class ConnectionRuntimeClientBinding implements RuntimeClientBinding {
  private readonly connection: RebindableConnection;
  readonly client: HostRuntimesClient;

  constructor(connection: Connection) {
    this.connection = new RebindableConnection(connection);
    this.client = createClient(hostRuntimesContract, this.connection);
  }

  rebind(source: RuntimeClientSource): boolean {
    if (!isConnectionSource(source)) return false;
    this.connection.rebind(source.connection);
    return true;
  }

  dispose(): void {
    this.connection.dispose();
  }
}

class DirectRuntimeClientBinding implements RuntimeClientBinding {
  constructor(readonly client: HostRuntimesClient) {}

  rebind(source: RuntimeClientSource): boolean {
    return !isConnectionSource(source) && source === this.client;
  }

  dispose(): void {
    // Direct clients are owned by their runtime worker.
  }
}

type RetainedAttachment = {
  readonly topic: string;
  readonly push: (update: LiveUpdate) => void;
  readonly options: AttachOptions;
  active: boolean;
  established: boolean;
  attempt?: object;
  unsubscribe?: Unsubscribe;
};

class RebindableConnection implements Connection {
  private readonly attachments = new Set<RetainedAttachment>();
  private readonly disconnectListeners = new Set<() => void>();
  private currentDisconnect: Unsubscribe = () => {};
  private generation = 0;
  private disposed = false;

  constructor(private current: Connection) {
    this.bindDisconnect();
  }

  rebind(connection: Connection): void {
    if (this.disposed || connection === this.current) return;
    this.currentDisconnect();
    this.current = connection;
    this.generation += 1;
    this.bindDisconnect();
    for (const attachment of this.attachments) {
      attachment.unsubscribe?.();
      attachment.unsubscribe = undefined;
      if (attachment.established) void this.reattach(attachment);
    }
  }

  call(
    path: string,
    input: unknown,
    options?: Parameters<Connection['call']>[2]
  ): Promise<unknown> {
    return this.current.call(path, input, options);
  }

  openBlobConsumer(channel: string): ReturnType<Connection['openBlobConsumer']> {
    return this.current.openBlobConsumer(channel);
  }

  openBlobProducer(
    channel: string,
    source: BlobSource
  ): ReturnType<Connection['openBlobProducer']> {
    return this.current.openBlobProducer(channel, source);
  }

  snapshot(topic: string): Promise<LiveSnapshot<unknown>> {
    return this.current.snapshot(topic);
  }

  async attach(
    topic: string,
    push: (update: LiveUpdate) => void,
    options: AttachOptions = {}
  ): Promise<Unsubscribe> {
    if (this.disposed) throw new WireError('DISCONNECTED', 'Runtime connection disposed');
    const attachment: RetainedAttachment = {
      topic,
      push,
      options,
      active: true,
      established: false,
    };
    this.attachments.add(attachment);
    try {
      while (attachment.active && !(await this.bindAttachment(attachment, false))) {
        // A newer Host generation superseded the attach; bind once to that generation.
      }
      if (!attachment.active) {
        throw new WireError('DISCONNECTED', 'Runtime connection disposed');
      }
      attachment.established = true;
    } catch (error) {
      attachment.active = false;
      this.attachments.delete(attachment);
      throw error;
    }
    return () => this.detach(attachment);
  }

  onDisconnect(callback: () => void): Unsubscribe {
    if (this.disposed) return () => {};
    this.disconnectListeners.add(callback);
    return () => this.disconnectListeners.delete(callback);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.currentDisconnect();
    for (const attachment of this.attachments) this.detach(attachment);
    this.disconnectListeners.clear();
  }

  private bindDisconnect(): void {
    const generation = this.generation;
    this.currentDisconnect = this.current.onDisconnect(() => {
      if (generation !== this.generation || this.disposed) return;
      for (const listener of this.disconnectListeners) listener();
    });
  }

  private async bindAttachment(
    attachment: RetainedAttachment,
    reattach: boolean
  ): Promise<boolean> {
    const connection = this.current;
    const generation = this.generation;
    const attempt = {};
    attachment.attempt = attempt;
    let unsubscribe: Unsubscribe;
    try {
      unsubscribe = await connection.attach(attachment.topic, attachment.push, attachment.options);
    } catch (error) {
      if (
        !attachment.active ||
        attachment.attempt !== attempt ||
        this.current !== connection ||
        this.generation !== generation
      ) {
        return false;
      }
      throw error;
    }
    if (
      !attachment.active ||
      attachment.attempt !== attempt ||
      this.current !== connection ||
      this.generation !== generation
    ) {
      unsubscribe();
      return false;
    }
    attachment.unsubscribe?.();
    attachment.unsubscribe = unsubscribe;
    if (reattach) attachment.options.onReattach?.();
    return true;
  }

  private async reattach(attachment: RetainedAttachment): Promise<void> {
    try {
      await this.bindAttachment(attachment, true);
    } catch (error) {
      if (!attachment.active) return;
      attachment.options.onReattachError?.(toWireError(error), { retrying: false });
    }
  }

  private detach(attachment: RetainedAttachment): void {
    if (!attachment.active) return;
    attachment.active = false;
    attachment.attempt = undefined;
    attachment.unsubscribe?.();
    attachment.unsubscribe = undefined;
    this.attachments.delete(attachment);
  }
}

function toWireError(error: unknown): WireError {
  if (error instanceof WireError) return error;
  return new WireError('DISCONNECTED', error instanceof Error ? error.message : String(error), {
    cause: error,
  });
}
