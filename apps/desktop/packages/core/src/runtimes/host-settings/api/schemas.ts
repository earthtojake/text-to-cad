import { z } from 'zod';

/**
 * Per-host default settings (spec: activation-scripts-via-terminals, host settings):
 * machine-level configuration that per-project settings may override. Stored as a
 * JSON file in the host's emdash data directory — readable and editable out-of-band.
 * Unknown keys in the file are preserved on update (forward compatibility).
 */
export const hostSettingsSchema = z.object({
  /** Shell bootstrap prepended to every script run on this host (nvm, mise, ...). */
  shellSetup: z.string().optional(),
  /** Default directory that new worktrees are created under. */
  worktreeRoot: z.string().optional(),
  /** Default tmux preference for terminal sessions on this host. */
  tmux: z.boolean().optional(),
  /**
   * File-watcher exclude globs applied at files-worker spawn (restart-applied).
   * Unset means "use the code-level defaults" (DEFAULT_WATCHER_EXCLUDE); an
   * empty array is a deliberate "exclude nothing". Defaults are never written
   * to the store so "unset" stays distinct from "user chose this".
   */
  watcherExclude: z.array(z.string()).optional(),
});

export type HostSettings = z.infer<typeof hostSettingsSchema>;

/** The wire-visible state: parsed settings plus the lenient-parse error flag. */
export const hostSettingsStateSchema = z.object({
  settings: hostSettingsSchema,
  /** True when the settings file existed but did not parse; defaults applied. */
  parseError: z.boolean(),
});

export type HostSettingsState = z.infer<typeof hostSettingsStateSchema>;

/**
 * Partial update: absent fields stay untouched, `null` clears a field back to
 * "unset". Unknown keys already in the file survive the write.
 */
export const updateHostSettingsInputSchema = z.object({
  shellSetup: z.string().nullable().optional(),
  worktreeRoot: z.string().nullable().optional(),
  tmux: z.boolean().nullable().optional(),
  watcherExclude: z.array(z.string()).nullable().optional(),
});

export type UpdateHostSettingsInput = z.infer<typeof updateHostSettingsInputSchema>;

export type ParseHostSettingsResult =
  | { success: true; data: HostSettings }
  | { success: false; data: HostSettings; error: unknown };

/** Lenient parse: a broken file degrades to empty defaults plus the error flag. */
export function parseHostSettings(content: string): ParseHostSettingsResult {
  try {
    return { success: true, data: hostSettingsSchema.parse(JSON.parse(content)) };
  } catch (error) {
    return { success: false, data: {}, error };
  }
}
