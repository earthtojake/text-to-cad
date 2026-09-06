import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppDb } from '@core/services/app-db/node/db';
import type { DrizzleClient } from './drizzleClient';
import { closeAppDb, getAppDb, getSqlite, resetAppDbForTests, setAppDb } from './instance';

afterEach(() => {
  resetAppDbForTests();
});

describe('app database instance', () => {
  it('throws before the database is initialized', () => {
    expect(() => getAppDb()).toThrow('App database has not been initialized');
    expect(() => getSqlite()).toThrow('App database has not been initialized');
  });

  it('publishes one concrete client', () => {
    const client = createClient();
    setAppDb(client);

    expect(getAppDb()).toBe(client.db);
    expect(getSqlite()).toBe(client.sqlite);
    expect(() => setAppDb(createClient())).toThrow('App database is already initialized');
  });

  it('closes and clears the client idempotently', () => {
    const client = createClient();
    setAppDb(client);

    closeAppDb();
    closeAppDb();

    expect(client.close).toHaveBeenCalledOnce();
    expect(() => getAppDb()).toThrow('App database has not been initialized');
  });

  it('clears the client even when close throws', () => {
    const client = createClient();
    vi.mocked(client.close).mockImplementation(() => {
      throw new Error('close failed');
    });
    setAppDb(client);

    expect(() => closeAppDb()).toThrow('close failed');
    expect(() => getAppDb()).toThrow('App database has not been initialized');
    expect(() => closeAppDb()).not.toThrow();
  });

  it('resets test state without closing the client', () => {
    const client = createClient();
    setAppDb(client);

    resetAppDbForTests();

    expect(client.close).not.toHaveBeenCalled();
    expect(() => getAppDb()).toThrow('App database has not been initialized');
  });
});

function createClient(): DrizzleClient {
  return {
    db: {} as AppDb,
    sqlite: {} as DrizzleClient['sqlite'],
    close: vi.fn(),
  };
}
