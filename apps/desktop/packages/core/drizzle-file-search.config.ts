import { defineConfig } from 'drizzle-kit';

export default defineConfig({
  schema: './src/runtimes/file-search/node/storage/schema.ts',
  out: './src/runtimes/file-search/node/storage/migrations',
  dialect: 'sqlite',
  strict: true,
  verbose: true,
});
