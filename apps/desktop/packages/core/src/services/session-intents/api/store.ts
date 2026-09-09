import { err, ok, type Result, type Serializable } from '@emdash/shared';
import { z } from 'zod';
import type { KeyValueStore } from '#primitives/kv/api';
import type { SessionIntent, SessionIntentError, SessionIntentScope } from './schemas';
import { sessionIntentSchema } from './schemas';

const STORE_KEY_PREFIX = 'session-intents';

export type SaveActiveSessionIntentInput = {
  conversationId: string;
  payload: Serializable;
  sessionId?: string | null;
};

export type SessionIntentStore = {
  list(): Promise<Result<SessionIntent[], SessionIntentError>>;
  saveActive(input: SaveActiveSessionIntentInput): Promise<Result<void, SessionIntentError>>;
  markSuspended(conversationId: string, cause: string): Promise<Result<void, SessionIntentError>>;
  remove(conversationId: string): Promise<Result<void, SessionIntentError>>;
};

export type CreateSessionIntentStoreOptions = {
  now?: () => number;
};

export function createNoopSessionIntentStore(): SessionIntentStore {
  return {
    async list() {
      return ok([]);
    },
    async saveActive() {
      return ok();
    },
    async markSuspended() {
      return ok();
    },
    async remove() {
      return ok();
    },
  };
}

export function sessionIntentFromActiveInput(
  input: SaveActiveSessionIntentInput,
  now: number
): SessionIntent {
  return {
    conversationId: input.conversationId,
    status: 'active',
    payload: input.payload,
    sessionId: input.sessionId,
    updatedAt: now,
  };
}

export function createKvSessionIntentStore(
  store: KeyValueStore,
  scope: SessionIntentScope,
  options: CreateSessionIntentStoreOptions = {}
): SessionIntentStore {
  const now = options.now ?? Date.now;
  const scopeKey = () => `${STORE_KEY_PREFIX}:${scope}`;
  const intentKey = (conversationId: string) => `${scopeKey()}:${conversationId}`;

  return {
    async list() {
      const loaded = await store.getAll();
      if (!loaded.success) return err(toSessionIntentError(loaded.error));

      const prefix = `${scopeKey()}:`;
      const result: SessionIntent[] = [];
      for (const [key, value] of Object.entries(loaded.data)) {
        if (!key.startsWith(prefix)) continue;
        const parsed = sessionIntentSchema.safeParse(value);
        if (!parsed.success) continue;
        result.push(parsed.data);
      }
      result.sort((a, b) => a.updatedAt - b.updatedAt);
      return ok(result);
    },

    async saveActive(input) {
      const intent = sessionIntentFromActiveInput(input, now());
      const saved = await store.set(
        intentKey(input.conversationId),
        intent as unknown as Serializable
      );
      if (!saved.success) return err(toSessionIntentError(saved.error));
      return ok();
    },

    async markSuspended(conversationId, cause) {
      const key = intentKey(conversationId);
      const loaded = await store.get(key);
      if (!loaded.success) return err(toSessionIntentError(loaded.error));
      if (loaded.data === null) return ok();

      const parsed = sessionIntentSchema.safeParse(loaded.data);
      if (!parsed.success) {
        return err({
          type: 'decode',
          key,
          message: z.prettifyError(parsed.error),
        });
      }

      const next: SessionIntent = {
        ...parsed.data,
        status: 'suspended',
        suspendedCause: cause,
        updatedAt: now(),
      };
      const saved = await store.set(key, next as unknown as Serializable);
      if (!saved.success) return err(toSessionIntentError(saved.error));
      return ok();
    },

    async remove(conversationId) {
      const deleted = await store.delete(intentKey(conversationId));
      if (!deleted.success) return err(toSessionIntentError(deleted.error));
      return ok();
    },
  };
}

export function createMemorySessionIntentStore(
  options: CreateSessionIntentStoreOptions = {}
): SessionIntentStore & { snapshot(): SessionIntent[] } {
  const now = options.now ?? Date.now;
  const intents = new Map<string, SessionIntent>();
  const success = (): Result<void, SessionIntentError> => ok();
  return {
    async list() {
      return ok(Array.from(intents.values()));
    },
    async saveActive(input: SaveActiveSessionIntentInput) {
      intents.set(input.conversationId, sessionIntentFromActiveInput(input, now()));
      return success();
    },
    async markSuspended(conversationId, cause) {
      const existing = intents.get(conversationId);
      if (!existing) return success();
      intents.set(conversationId, {
        ...existing,
        status: 'suspended',
        suspendedCause: cause,
        updatedAt: now(),
      });
      return success();
    },
    async remove(conversationId) {
      intents.delete(conversationId);
      return success();
    },
    snapshot() {
      return Array.from(intents.values());
    },
  };
}

function toSessionIntentError(error: { message: string; key?: string }): SessionIntentError {
  return { type: 'io', message: error.message, key: error.key };
}
