import z from 'zod';

export const EMDASH_CONFIG_FILE = '.hardcore.json';

export function isEmdashConfigPath(filePath: string): boolean {
  const normalized = filePath.replace(/\\/g, '/');
  return normalized === EMDASH_CONFIG_FILE || normalized.endsWith(`/${EMDASH_CONFIG_FILE}`);
}

const preservePatternsSchema = z
  .array(z.string())
  .transform((patterns) => patterns.filter((pattern) => pattern !== EMDASH_CONFIG_FILE));

export const emdashScriptsConfigSchema = z.object({
  prepare: z.string().optional(),
  setup: z.string().optional(),
  run: z.string().optional(),
  teardown: z.string().optional(),
});

/**
 * Stale keys from retired features (e.g. `excludePatterns`) are silently stripped by
 * the non-strict object parse, so older project config files keep parsing cleanly.
 */
export const emdashConfigSchema = z.object({
  /** Gitignored files deliberately carried into new worktrees; empty unless configured. */
  preservePatterns: preservePatternsSchema.optional(),
  shellSetup: z.string().optional(),
  scripts: emdashScriptsConfigSchema.optional(),
});

export type EmdashConfig = z.infer<typeof emdashConfigSchema>;
export type EmdashScriptsConfig = z.infer<typeof emdashScriptsConfigSchema>;

export type ParseEmdashConfigResult =
  | { success: true; data: EmdashConfig }
  | { success: false; data: EmdashConfig; error: unknown };

export function defaultEmdashConfig(): EmdashConfig {
  return emdashConfigSchema.parse({});
}

export function parseEmdashConfig(content: string): ParseEmdashConfigResult {
  try {
    return { success: true, data: emdashConfigSchema.parse(JSON.parse(content)) };
  } catch (error) {
    return { success: false, data: defaultEmdashConfig(), error };
  }
}
