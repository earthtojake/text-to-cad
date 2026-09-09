import { err, ok, type Result } from '@emdash/shared';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { cell, expose, type Cell } from '@emdash/wire/state';
import type { StoreHandle } from '#primitives/sqlite-store/api';
import { conversationsContract } from '../api/contract';
import type {
  ConversationMutationError,
  CreateConversationError,
  DeleteConversationError,
} from '../api/errors';
import type {
  ConversationRecord,
  ConversationRecords,
  CreateConversationInput,
  DeleteConversationInput,
  RenameConversationInput,
  ReportProviderSessionIdInput,
  ReportSessionActivityInput,
  ReportSessionEndedInput,
  ReportSessionStartedInput,
  UpdateConversationConfigInput,
} from '../api/schemas';
import { ConversationRecordStore } from './persistence/record-store';
import type { ConversationsDb } from './persistence/store';

export type ConversationsRuntimeOptions = {
  handle: StoreHandle<ConversationsDb>;
  clock?: Clock;
  logger?: Logger;
};

const IMMUTABLE_CREATE_FIELDS = [
  'provider',
  'type',
  'cwd',
  'workspacePath',
  'idRegime',
  'createdAt',
] as const;

/**
 * The sole writer of the conversation index (spec §3.3, conv.sole-writer): clients mutate
 * only through the wire verbs below; session runtimes report lifecycle facts through the
 * report surface (ticket 12). Nothing else touches the storage.
 */
export class ConversationsRuntime {
  private readonly store: ConversationRecordStore;
  private readonly clock: Clock;
  private readonly logger: Logger;
  private readonly recordsCell: Cell<ConversationRecords>;
  readonly recordsHost: LeasedLiveModelProvider<typeof conversationsContract.records>;

  constructor(options: ConversationsRuntimeOptions) {
    this.clock = options.clock ?? systemClock;
    this.logger = options.logger ?? noopLogger;
    this.store = new ConversationRecordStore(options.handle);

    const initial: ConversationRecords = {};
    for (const record of this.store.list()) {
      initial[record.conversationId] = record;
    }
    this.recordsCell = cell<ConversationRecords>(initial, { name: 'conversation-records' });
    this.recordsHost = expose(conversationsContract.records, {
      list: () => this.recordsCell,
    });
  }

  dispose(): void {
    this.recordsHost.dispose();
  }

  create(input: CreateConversationInput): Result<ConversationRecord, CreateConversationError> {
    const existing = this.store.get(input.conversationId);
    if (existing) {
      const mismatched = IMMUTABLE_CREATE_FIELDS.filter(
        (field) => existing[field] !== input[field]
      );
      if (mismatched.length > 0) {
        return err({
          type: 'immutable-field-mismatch',
          conversationId: input.conversationId,
          fields: [...mismatched],
          message: `Conversation '${input.conversationId}' already exists with different immutable fields: ${mismatched.join(', ')}`,
        });
      }
      // Idempotent replay: same id, identical immutable fields — no-op success (spec §4.2).
      return ok(existing);
    }

    const record: ConversationRecord = {
      conversationId: input.conversationId,
      provider: input.provider,
      type: input.type,
      cwd: input.cwd,
      workspacePath: input.workspacePath,
      idRegime: input.idRegime,
      createdAt: input.createdAt,
      title: input.title,
      config: input.config,
      providerSessionId: null,
      providerSessionIdObservedAt: null,
      lastSessionActivityAt: null,
      lastSpawnedAt: null,
      lastResumeOutcome: 'never-resumed',
      updatedAt: this.clock.now(),
    };
    this.store.insert(record);
    this.publish(record);
    return ok(record);
  }

  rename(input: RenameConversationInput): Result<ConversationRecord, ConversationMutationError> {
    return this.mutate(input.conversationId, (record) => ({ ...record, title: input.title }));
  }

  updateConfig(
    input: UpdateConversationConfigInput
  ): Result<ConversationRecord, ConversationMutationError> {
    return this.mutate(input.conversationId, (record) => ({ ...record, config: input.config }));
  }

  delete(input: DeleteConversationInput): Result<void, DeleteConversationError> {
    const deleted = this.store.delete(input.conversationId);
    if (deleted) {
      this.recordsCell.update((previous) => {
        const next = { ...previous };
        delete next[input.conversationId];
        return next;
      });
    } else {
      this.logger.debug?.(
        `delete of absent conversation '${input.conversationId}' — idempotent no-op`
      );
    }
    return ok(undefined);
  }

  reportSessionStarted(input: ReportSessionStartedInput): Result<void, ConversationMutationError> {
    const now = this.clock.now();
    return dropData(
      this.mutate(input.conversationId, (record) => ({
        ...record,
        lastSpawnedAt: now,
        ...(input.providerSessionId === null
          ? {}
          : { providerSessionId: input.providerSessionId, providerSessionIdObservedAt: now }),
        ...(input.resumeOutcome === null ? {} : { lastResumeOutcome: input.resumeOutcome }),
      }))
    );
  }

  reportProviderSessionId(
    input: ReportProviderSessionIdInput
  ): Result<void, ConversationMutationError> {
    const now = this.clock.now();
    return dropData(
      this.mutate(input.conversationId, (record) => ({
        ...record,
        providerSessionId: input.providerSessionId,
        providerSessionIdObservedAt: now,
      }))
    );
  }

  reportSessionActivity(
    input: ReportSessionActivityInput
  ): Result<void, ConversationMutationError> {
    const now = this.clock.now();
    return dropData(
      this.mutate(input.conversationId, (record) => ({ ...record, lastSessionActivityAt: now }))
    );
  }

  reportSessionEnded(input: ReportSessionEndedInput): Result<void, ConversationMutationError> {
    const now = this.clock.now();
    return dropData(
      this.mutate(input.conversationId, (record) => ({ ...record, lastSessionActivityAt: now }))
    );
  }

  private mutate(
    id: string,
    change: (record: ConversationRecord) => ConversationRecord
  ): Result<ConversationRecord, ConversationMutationError> {
    const existing = this.store.get(id);
    if (!existing) {
      return err({
        type: 'conversation-not-found',
        conversationId: id,
        message: `Conversation '${id}' does not exist in the index`,
      });
    }
    const updated = { ...change(existing), updatedAt: this.clock.now() };
    this.store.update(updated);
    this.publish(updated);
    return ok(updated);
  }

  private publish(record: ConversationRecord): void {
    this.recordsCell.update((previous) => ({ ...previous, [record.conversationId]: record }));
  }
}

function dropData<E>(result: Result<unknown, E>): Result<void, E> {
  return result.success ? ok(undefined) : result;
}
