import { defineConfig } from 'drizzle-kit';

export default defineConfig({
  schema: './src/runtimes/conversations/node/persistence/schema.ts',
  out: './src/runtimes/conversations/node/persistence/migrations',
  dialect: 'sqlite',
  strict: true,
  verbose: true,
});
