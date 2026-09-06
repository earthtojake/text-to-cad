import type { Unsubscribe } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import type { Clock, RetrySchedule } from '@emdash/shared/scheduling';
import type { ContractClient } from '../api/client';
import type { Contract, ContractDefinitions } from '../api/define';
import type { WireInstrumentation } from '../api/instrumentation';
import type {
  ProvidedWireComponentRequirements,
  WireComponentDefinition,
  WireComponentRequirements,
} from './component';

export const WORKER_NAME_ENV_VAR = 'EMDASH_WORKER_NAME';

export type WorkerStdioStream = 'stdout' | 'stderr';

export type ProcessExit = {
  code: number | null;
  signal?: string | null;
};

export type WorkerProcessSpec = {
  entry: string;
  args?: readonly string[];
  env?: Record<string, string | undefined>;
  cwd?: string;
};

export interface WorkerProcess {
  readonly pid: number | undefined;
  send(message: unknown): void;
  onMessage(cb: (message: unknown) => void): Unsubscribe;
  onExit(cb: (exit: ProcessExit) => void): Unsubscribe;
  onStdio(cb: (stream: WorkerStdioStream, chunk: string) => void): Unsubscribe;
  kill(): void | Promise<void>;
}

export interface WorkerProcessSpawner {
  spawn(spec: WorkerProcessSpec, scope: Scope): Promise<WorkerProcess>;
}

export type WorkerSupervision =
  | {
      restart: 'never';
    }
  | {
      restart: 'on-failure';
      schedule: RetrySchedule;
    };

export type WireWorkerState =
  | { kind: 'idle' }
  | { kind: 'starting'; generation: number; attempt: number }
  | { kind: 'ready'; generation: number; attempt: number; pid?: number }
  | { kind: 'restarting'; generation: number; attempt: number; lastExit: ProcessExit }
  | { kind: 'failed'; attempts: number; error?: unknown; lastExit?: ProcessExit }
  | { kind: 'stopping' }
  | { kind: 'disposed' };

export interface WireWorker<Defs extends ContractDefinitions> {
  readonly name: string;
  readonly contract: Contract<Defs>;
  readonly state: WireWorkerState;
  ready(): Promise<ContractClient<Defs>>;
  stop(): Promise<void>;
  restart(reason?: unknown): Promise<void>;
  onStateChanged(cb: (state: WireWorkerState) => void): Unsubscribe;
}

export type WireWorkerDefinition<Defs extends ContractDefinitions> = {
  name: string;
  contract: Contract<Defs>;
  process: () => WorkerProcessSpec;
  setup?(context: {
    generation: number;
    process: WorkerProcess;
    scope: Scope;
  }): void | Promise<void>;
  supervision?: WorkerSupervision;
  readyTimeoutMs?: number;
  shutdownGraceMs?: number;
  instrumentation?: WireInstrumentation;
};

export type WireComponentWorkerCreateOptions<
  Requirements extends WireComponentRequirements,
  Config,
> = {
  name?: string;
  executable: string;
  args?: readonly string[];
  env?: Record<string, string | undefined>;
  cwd?: string;
  dependencies: ProvidedWireComponentRequirements<Requirements>;
  config: Config;
  supervision?: WorkerSupervision;
  readyTimeoutMs?: number;
  shutdownGraceMs?: number;
  instrumentation?: WireInstrumentation;
};

export type WireWorkerHostOptions = {
  scope: Scope;
  processSpawner: WorkerProcessSpawner;
  clock?: Clock;
  logger?: Logger;
  defaults?: {
    readyTimeoutMs?: number;
    shutdownGraceMs?: number;
    supervision?: WorkerSupervision;
  };
};

export interface WireWorkerHost {
  readonly scope: Scope;
  create<
    Id extends string,
    Defs extends ContractDefinitions,
    Requirements extends WireComponentRequirements,
    Config,
  >(
    component: WireComponentDefinition<Id, Defs, Requirements, Config>,
    options: WireComponentWorkerCreateOptions<Requirements, Config>
  ): WireWorker<Defs>;
  spawn<
    Id extends string,
    Defs extends ContractDefinitions,
    Requirements extends WireComponentRequirements,
    Config,
  >(
    component: WireComponentDefinition<Id, Defs, Requirements, Config>,
    options: WireComponentWorkerCreateOptions<Requirements, Config>
  ): Promise<ContractClient<Defs>>;
  dispose(): Promise<void>;
}

export type WorkerParentPort = {
  send(message: unknown): void;
  onMessage(cb: (message: unknown) => void): Unsubscribe;
  onDisconnect(cb: () => void): Unsubscribe;
};
