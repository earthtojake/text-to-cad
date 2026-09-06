import { defineConfig } from 'drizzle-kit';

export default defineConfig({
  schema: './src/runtimes/workspace-registry/node/persistence/schema.ts',
  out: './src/runtimes/workspace-registry/node/persistence/migrations',
  dialect: 'sqlite',
  strict: true,
  verbose: true,
});
