export type AppWorktreeRootMigrationDeps = {
  getAppDefaultWorktreeDirectoryOverride(): Promise<string | undefined>;
  clearAppDefaultWorktreeDirectory(): Promise<void>;
  localHostSettings: {
    getWorktreeRoot(): Promise<
      { success: true; worktreeRoot: string | undefined } | { success: false }
    >;
    setWorktreeRoot(worktreeRoot: string): Promise<{ success: boolean }>;
  };
};

/**
 * Moves the retired app-wide worktree directory to the local host default.
 * Throws before clearing the source when host persistence fails so mount retries.
 */
export async function migrateAppWorktreeRootToLocalHostDefault(
  deps: AppWorktreeRootMigrationDeps
): Promise<void> {
  const override = await deps.getAppDefaultWorktreeDirectoryOverride();
  if (override === undefined) return;

  const trimmed = override.trim();
  if (trimmed) {
    const current = await deps.localHostSettings.getWorktreeRoot();
    if (!current.success) {
      throw new Error('app worktree-root migration: local host settings unavailable');
    }
    if (current.worktreeRoot === undefined) {
      const updated = await deps.localHostSettings.setWorktreeRoot(trimmed);
      if (!updated.success) {
        throw new Error('app worktree-root migration: failed to write local host default');
      }
    }
  }

  await deps.clearAppDefaultWorktreeDirectory();
}
