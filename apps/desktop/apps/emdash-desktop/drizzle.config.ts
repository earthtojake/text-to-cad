import { resolve } from 'node:path';
import { defineConfig } from 'drizzle-kit';
import { defaultDbFilePath, resolveDefaultUserDataPath } from './src/main/db/default-path';

function resolveDbUrl(): string {
  const explicit = process.env.EMDASH_DB_FILE?.trim();
  if (explicit) {
    return resolve(explicit);
  }
  return defaultDbFilePath(resolveDefaultUserDataPath());
}

export default defineConfig({
  schema: './src/core/services/app-db/node/schema.ts',
  out: './drizzle',
  dialect: 'sqlite',
  dbCredentials: {
    url: resolveDbUrl(),
  },
  strict: true,
  verbose: true,
});
