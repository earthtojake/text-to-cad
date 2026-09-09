import { defineConfig } from 'drizzle-kit';

export default defineConfig({
  schema: './src/runtimes/automations/node/persistence/schema.ts',
  out: './src/runtimes/automations/node/persistence/migrations',
  dialect: 'sqlite',
  strict: true,
  verbose: true,
});
