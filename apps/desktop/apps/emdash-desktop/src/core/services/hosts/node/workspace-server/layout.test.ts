import { describe, expect, it } from 'vitest';
import { validateWorkspaceServerVersion, workspaceServerLayout } from './layout';

describe('workspaceServerLayout', () => {
  it('derives every managed path from the remote home', () => {
    const layout = workspaceServerLayout('/home/dev user');

    expect(layout.root).toBe('/home/dev user/.emdash/workspace-server');
    expect(layout.versionDirectory('1.2.3-canary.1')).toBe(
      '/home/dev user/.emdash/workspace-server/versions/1.2.3-canary.1'
    );
    expect(layout.currentLauncher).toBe(
      '/home/dev user/.emdash/workspace-server/current/bin/emdash-workspace-server'
    );
    expect(layout.socketPath).toBe('/home/dev user/.emdash/workspace-server/run/workspace.sock');
  });

  it('rejects unsafe homes and version components', () => {
    expect(() => workspaceServerLayout('relative/home')).toThrow('Invalid remote home');
    expect(() => workspaceServerLayout('/home/user\nother')).toThrow('Invalid remote home');
    expect(() => validateWorkspaceServerVersion('../1.2.3')).toThrow(
      'Invalid workspace-server version'
    );
    expect(() => validateWorkspaceServerVersion('1.2.3; rm -rf /')).toThrow(
      'Invalid workspace-server version'
    );
  });
});
