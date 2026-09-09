export interface TaskEnvContext {
  taskId: string;
  taskName: string;
  taskPath: string;
  projectPath: string;
  /**
   * The effective default branch from the blessed resolver; `null`/absent when
   * the repository has none (the env var is then omitted rather than invented).
   */
  defaultBranch?: string | null;
  portSeed?: string;
}

export function getTaskEnvVars(ctx: TaskEnvContext): Record<string, string> {
  const taskName = slugify(ctx.taskName) || 'task';
  const portSeed = ctx.portSeed || ctx.taskPath || ctx.taskId;
  return {
    EMDASH_TASK_ID: ctx.taskId,
    EMDASH_TASK_NAME: taskName,
    EMDASH_TASK_PATH: ctx.taskPath,
    EMDASH_ROOT_PATH: ctx.projectPath,
    ...(ctx.defaultBranch ? { EMDASH_DEFAULT_BRANCH: ctx.defaultBranch } : {}),
    EMDASH_PORT: String(getBasePort(portSeed)),
  };
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

function getBasePort(seed: string): number {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  return 50000 + (Math.abs(hash) % 1000) * 10;
}
