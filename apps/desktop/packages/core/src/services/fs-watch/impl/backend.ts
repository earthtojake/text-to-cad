import type { Scope } from '@emdash/shared/concurrency';
import type { WatchEvent } from '#services/fs-watch/api';

export type WatchKey = {
  root: string;
  ignore: string[];
};

export type WatchSink = {
  events(events: WatchEvent[]): void;
  resync(): void;
};

export type WatchOnError = (context: string, error: unknown) => void;

export interface WatchBackend {
  subscribe(key: WatchKey, sink: WatchSink, scope: Scope): Promise<void>;
  dispose?(): Promise<void> | void;
}
