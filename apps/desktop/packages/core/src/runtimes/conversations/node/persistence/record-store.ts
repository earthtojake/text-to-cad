import { eq } from 'drizzle-orm';
import type { StoreHandle } from '#primitives/sqlite-store/api';
import type { ConversationRecord } from '../../api/schemas';
import {
  parseConfigPayload,
  parseProviderLinkPayload,
  serializeConfigPayload,
  serializeProviderLinkPayload,
} from './payload-codecs';
import { conversationRecords } from './schema';
import type { ConversationsDb } from './store';

type Row = typeof conversationRecords.$inferSelect;

export class ConversationRecordStore {
  constructor(private readonly handle: StoreHandle<ConversationsDb>) {}

  list(): ConversationRecord[] {
    return this.handle.db.select().from(conversationRecords).all().map(rowToRecord);
  }

  get(id: string): ConversationRecord | null {
    const row = this.handle.db
      .select()
      .from(conversationRecords)
      .where(eq(conversationRecords.id, id))
      .get();
    return row ? rowToRecord(row) : null;
  }

  insert(record: ConversationRecord): void {
    this.handle.db.insert(conversationRecords).values(recordToRow(record)).run();
  }

  update(record: ConversationRecord): void {
    const { id, ...columns } = recordToRow(record);
    this.handle.db
      .update(conversationRecords)
      .set(columns)
      .where(eq(conversationRecords.id, id))
      .run();
  }

  delete(id: string): boolean {
    const result = this.handle.db
      .delete(conversationRecords)
      .where(eq(conversationRecords.id, id))
      .run();
    return result.changes > 0;
  }
}

function rowToRecord(row: Row): ConversationRecord {
  const link = parseProviderLinkPayload(row.providerLink);
  return {
    conversationId: row.id,
    provider: row.provider,
    type: row.type,
    cwd: row.cwd,
    workspacePath: row.workspacePath,
    idRegime: link.idRegime,
    createdAt: row.createdAt,
    title: row.title,
    config: parseConfigPayload(row.config),
    providerSessionId: link.providerSessionId,
    providerSessionIdObservedAt: link.observedAt,
    lastSessionActivityAt: row.lastSessionActivityAt,
    lastSpawnedAt: row.lastSpawnedAt,
    lastResumeOutcome: row.lastResumeOutcome,
    updatedAt: row.updatedAt,
  };
}

function recordToRow(record: ConversationRecord): Row {
  return {
    id: record.conversationId,
    provider: record.provider,
    type: record.type,
    cwd: record.cwd,
    workspacePath: record.workspacePath,
    createdAt: record.createdAt,
    title: record.title,
    config: serializeConfigPayload(record.config),
    providerLink: serializeProviderLinkPayload({
      providerSessionId: record.providerSessionId,
      idRegime: record.idRegime,
      observedAt: record.providerSessionIdObservedAt,
    }),
    lastSessionActivityAt: record.lastSessionActivityAt,
    lastSpawnedAt: record.lastSpawnedAt,
    lastResumeOutcome: record.lastResumeOutcome,
    updatedAt: record.updatedAt,
  };
}
