import { z } from 'zod';
import { log } from './logger';

const buildSchema = z.object({
  VITE_POSTHOG_KEY: z.string().optional(),
  VITE_POSTHOG_HOST: z.string().optional(),
  VITE_BUILD: z.enum(['canary', 'prod']).default('prod'),
});

// Dev-only overrides: read from process.env (supports non-VITE_ prefixed vars,
// loaded from .env.local via electron-vite's envDir but never shipped in prod)
const devSchema = z.object({
  POSTHOG_PROJECT_API_KEY: z.string().optional(),
  POSTHOG_HOST: z.string().optional(),
});

function parseSection<T extends z.ZodRawShape>(
  schema: z.ZodObject<T>,
  source: Record<string, unknown>,
  label: string
): z.infer<z.ZodObject<T>> {
  const result = schema.safeParse(source);
  if (!result.success) {
    log.error(`[env:${label}] Failed to parse environment variables`, { error: result.error });
    return {} as z.infer<z.ZodObject<T>>;
  }
  return result.data;
}

export const env = {
  build: parseSection(buildSchema, import.meta.env as unknown as Record<string, unknown>, 'build'),
  dev: import.meta.env.DEV
    ? parseSection(devSchema, process.env, 'dev')
    : ({} as z.infer<typeof devSchema>),
};
