import type Database from 'better-sqlite3';
import type { AppDb } from '@core/services/app-db/node/db';
import type { DrizzleClient } from './drizzleClient';

let client: DrizzleClient | undefined;

function requireClient(): DrizzleClient {
  if (!client) {
    throw new Error('App database has not been initialized');
  }
  return client;
}

export function setAppDb(nextClient: DrizzleClient): void {
  if (client) {
    throw new Error('App database is already initialized');
  }
  client = nextClient;
}

export function getAppDb(): AppDb {
  return requireClient().db;
}

export function getSqlite(): Database.Database {
  return requireClient().sqlite;
}

export function resetAppDbForTests(): void {
  client = undefined;
}

export function closeAppDb(): void {
  const currentClient = client;
  if (!currentClient) return;

  client = undefined;
  currentClient.close();
}
