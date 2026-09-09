import { describe, expect, it } from 'vitest';
import { buildScriptEnv } from './env';

describe('buildScriptEnv', () => {
  it('derives all six EMDASH_* vars from workspace facts', () => {
    const env = buildScriptEnv('/work/trees/my-feature', {
      workspaceId: 'ws-1',
      repositoryPath: '/repos/app',
      branch: 'feature/My Branch',
      defaultBranch: 'origin/main',
    });
    expect(env).toEqual({
      EMDASH_TASK_ID: 'ws-1',
      EMDASH_TASK_NAME: 'feature-my-branch',
      EMDASH_TASK_PATH: '/work/trees/my-feature',
      EMDASH_ROOT_PATH: '/repos/app',
      EMDASH_DEFAULT_BRANCH: 'origin/main',
      EMDASH_PORT: expect.stringMatching(/^5\d{4}$/) as unknown as string,
    });
  });

  it('falls back to directory name and workspace path, omitting the default branch, when facts are sparse', () => {
    const env = buildScriptEnv('/work/trees/task-42', { workspaceId: 'ws-2' });
    expect(env.EMDASH_TASK_NAME).toBe('task-42');
    expect(env.EMDASH_ROOT_PATH).toBe('/work/trees/task-42');
    expect(Object.keys(env)).not.toContain('EMDASH_DEFAULT_BRANCH');
  });

  it('never sets CI and derives a stable port from the workspace path', () => {
    const first = buildScriptEnv('/work/a', { workspaceId: 'x' });
    const second = buildScriptEnv('/work/a', { workspaceId: 'y' });
    expect(first.EMDASH_PORT).toBe(second.EMDASH_PORT);
    expect(Object.keys(first)).not.toContain('CI');
    const port = Number(first.EMDASH_PORT);
    expect(port).toBeGreaterThanOrEqual(50_000);
    expect(port).toBeLessThan(60_000);
  });

  it('degenerate branch names still yield a non-empty task name', () => {
    const env = buildScriptEnv('/work/trees/x', { workspaceId: 'ws', branch: '///' });
    expect(env.EMDASH_TASK_NAME).toBe('task');
  });
});
