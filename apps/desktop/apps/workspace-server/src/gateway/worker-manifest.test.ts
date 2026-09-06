import { describe, expect, it } from 'vitest';
import { workspaceWorkerBuildInputs } from './worker-manifest';
import { workspaceWorkerPath } from './worker-paths';

const runtimeIds = [
  'acp',
  'agent-config',
  'conversations',
  'file-search',
  'files',
  'git',
  'host-settings',
  'resource-usage',
  'scripts',
  'terminals',
  'tui-agents',
  'workspace-registry',
] as const;

describe('workspace worker manifest', () => {
  it('packages every core runtime and the shared filesystem watcher', () => {
    const entries = workspaceWorkerBuildInputs();

    expect(Object.keys(entries).sort()).toEqual(
      [...runtimeIds.map((id) => `${id}-runtime`), 'fs-watch-runtime'].sort()
    );
    for (const id of runtimeIds) {
      expect(workspaceWorkerPath(id).endsWith(`${id}-runtime.mjs`)).toBe(true);
    }
  });
});
