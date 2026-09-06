export * from '#services/session-intents/api';

import { createJsonFileKeyValueStore } from '#primitives/kv/node';
import {
  createKvSessionIntentStore,
  type SessionIntentScope,
  type SessionIntentStore,
} from '#services/session-intents/api';

export type FileSessionIntentStoreOptions = {
  path: string;
  scope: SessionIntentScope;
};

export function createFileSessionIntentStore(
  options: FileSessionIntentStoreOptions
): SessionIntentStore {
  return createKvSessionIntentStore(
    createJsonFileKeyValueStore({ path: options.path }),
    options.scope
  );
}
