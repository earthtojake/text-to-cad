import { err, ok, type Result } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { expose, family, query, type Family, type Query } from '@emdash/wire/state';
import {
  mementoKeyId,
  mementosWireContract,
  type MementoModelKey,
  type MementoMutationError,
  type MementoRow,
} from '@core/primitives/mementos/api';
import type { Subject } from '@core/primitives/subjects/api';
import type { MementoPersistenceService, MementoSweepPolicy } from './persistence';
import { matchMementoKey, mementoPokes } from './pokes';

export interface MementoServiceOptions {
  readonly persistence: MementoPersistenceService;
  readonly scope?: Scope;
  readonly idleTtlMs?: number;
  readonly now?: () => number;
}

export class MementoService {
  readonly host: LeasedLiveModelProvider<typeof mementosWireContract.memento>;

  private readonly persistence: MementoPersistenceService;
  private readonly scope: Scope;
  private readonly now: () => number;
  private readonly states: Family<MementoModelKey, Query<MementoRow | null>>;

  constructor(options: MementoServiceOptions) {
    this.persistence = options.persistence;
    this.scope = options.scope ?? createScope({ label: 'mementos-service' });
    this.now = options.now ?? Date.now;
    this.states = family<MementoModelKey, Query<MementoRow | null>>(
      (key, scope) =>
        query({
          fetch: async () => this.persistence.getRow(key),
          pokes: [mementoPokes.value.subscription(matchMementoKey(key))],
          scope,
        }),
      {
        scope: this.scope,
        name: 'memento-states',
        lingerMs: options.idleTtlMs ?? 30_000,
        key: mementoKeyId,
      }
    );
    this.host = expose(
      mementosWireContract.memento,
      {
        value: (key, scope) => {
          const release = this.states.retain(key);
          scope.add(release);
          return this.states(key);
        },
      },
      {
        mutations: {
          save: async (context) =>
            this.runPersistenceMutation(async () => {
              const row = { ...context.input, updatedAt: this.now() };
              this.persistence.upsert(context.key, row);
              const revision = this.states(context.key).settle(row, {
                mutationIds: [context.mutationId],
              });
              await context.observed('value', revision);
            }),
          reset: async (context) =>
            this.runPersistenceMutation(async () => {
              this.persistence.deleteRow(context.key);
              const revision = this.states(context.key).settle(null, {
                mutationIds: [context.mutationId],
              });
              await context.observed('value', revision);
            }),
        },
      }
    );

    this.scope.add(() => this.host.dispose());
    this.scope.add(() => this.persistence.close());
  }

  deleteBySubject(subject: Subject): Result<{ deleted: number }, MementoMutationError> {
    try {
      const deleted = this.persistence.deleteBySubject(subject);
      mementoPokes.value.poke({ subjectKind: subject.kind, subjectKey: subject.key });
      return ok({ deleted });
    } catch (error) {
      return err(toMementoError(error));
    }
  }

  deleteAll(): Result<{ deleted: number }, MementoMutationError> {
    try {
      const deleted = this.persistence.deleteAll();
      mementoPokes.value.poke({});
      return ok({ deleted });
    } catch (error) {
      return err(toMementoError(error));
    }
  }

  deleteOrphans(
    kind: string,
    validKeys: readonly string[]
  ): Result<{ deleted: number }, MementoMutationError> {
    try {
      const { deleted, orphanKeys } = this.persistence.deleteOrphans(kind, validKeys);
      if (orphanKeys.length === 0) return ok({ deleted });
      mementoPokes.value.poke({ subjectKind: kind });
      return ok({ deleted });
    } catch (error) {
      return err(toMementoError(error));
    }
  }

  sweep(policies: readonly MementoSweepPolicy[], now = Date.now()): number {
    return this.persistence.sweep(policies, now);
  }

  async dispose(): Promise<void> {
    await this.scope.dispose();
  }

  private async runPersistenceMutation(
    operation: () => Promise<void>
  ): Promise<Result<void, MementoMutationError>> {
    try {
      await operation();
      return ok<void>();
    } catch (error) {
      return err(toMementoError(error));
    }
  }
}

function toMementoError(error: unknown): MementoMutationError {
  return {
    code: 'persistence',
    message: error instanceof Error ? error.message : String(error),
  };
}
