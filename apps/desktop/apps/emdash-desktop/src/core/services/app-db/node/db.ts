import type { drizzle } from 'drizzle-orm/better-sqlite3';
import type * as schema from './schema';

export type AppDb = ReturnType<typeof drizzle<typeof schema>>;
export type DrizzleTx = Parameters<AppDb['transaction']>[0] extends (tx: infer T) => unknown
  ? T
  : never;
