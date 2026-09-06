import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { workspaceServerRuntimePaths } from './paths';

describe('workspaceServerRuntimePaths', () => {
  it('places state beside a custom socket instead of in its parent directory', () => {
    const paths = workspaceServerRuntimePaths('/tmp/emdash-test/workspace.sock');

    expect(paths.rootDirectory).toBe('/tmp/emdash-test');
    expect(paths.stateDirectory).toBe('/tmp/emdash-test/state');
  });

  it('keeps the conventional run and state directories as siblings', () => {
    const root = join('/tmp', 'emdash-test');
    const paths = workspaceServerRuntimePaths(join(root, 'run', 'workspace.sock'));

    expect(paths.rootDirectory).toBe(root);
    expect(paths.stateDirectory).toBe(join(root, 'state'));
  });
});
