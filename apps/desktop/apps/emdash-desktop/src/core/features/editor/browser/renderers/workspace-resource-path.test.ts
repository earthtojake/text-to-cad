import { describe, expect, it } from 'vitest';
import { resolveWorkspaceResourcePath } from '@core/features/editor/api/browser/renderers/workspace-resource-path';

const workspacePath = '/repo';

describe('resolveWorkspaceResourcePath', () => {
  it('resolves relative resources against the containing file directory', () => {
    expect(
      resolveWorkspaceResourcePath({
        workspacePath,
        containingFilePath: '/repo/docs/readme.md',
        resourcePath: 'images/logo.png',
      })
    ).toBe('/repo/docs/images/logo.png');
  });

  it('anchors root-anchored resources at the workspace root, not the machine root', () => {
    expect(
      resolveWorkspaceResourcePath({
        workspacePath,
        containingFilePath: '/repo/docs/readme.md',
        resourcePath: '/assets/a.png',
      })
    ).toBe('/repo/assets/a.png');
  });

  it('resolves parent traversal that stays inside the workspace', () => {
    expect(
      resolveWorkspaceResourcePath({
        workspacePath,
        containingFilePath: '/repo/docs/readme.md',
        resourcePath: '../assets/a.png',
      })
    ).toBe('/repo/assets/a.png');
  });

  it('returns null when a resource escapes the workspace root', () => {
    expect(
      resolveWorkspaceResourcePath({
        workspacePath,
        containingFilePath: '/repo/readme.md',
        resourcePath: '../secrets.txt',
      })
    ).toBeNull();
    expect(
      resolveWorkspaceResourcePath({
        workspacePath,
        containingFilePath: '/repo/docs/readme.md',
        resourcePath: '/../../etc/passwd',
      })
    ).toBeNull();
  });

  it('returns null for external and special references', () => {
    for (const resourcePath of [
      'https://example.com/a.png',
      'data:image/png;base64,xxxx',
      'mailto:a@b.com',
      '//cdn.example.com/a.png',
      '#anchor',
    ]) {
      expect(
        resolveWorkspaceResourcePath({
          workspacePath,
          containingFilePath: '/repo/readme.md',
          resourcePath,
        })
      ).toBeNull();
    }
  });

  it('fails closed when the workspace root is unknown', () => {
    expect(
      resolveWorkspaceResourcePath({
        workspacePath: undefined,
        containingFilePath: '/repo/readme.md',
        resourcePath: 'images/logo.png',
      })
    ).toBeNull();
  });

  it('strips query and fragment before resolving', () => {
    expect(
      resolveWorkspaceResourcePath({
        workspacePath,
        containingFilePath: '/repo/readme.md',
        resourcePath: 'images/logo.png?v=2#x',
      })
    ).toBe('/repo/images/logo.png');
  });

  it('supports Windows-drive workspace roots', () => {
    expect(
      resolveWorkspaceResourcePath({
        workspacePath: 'C:/repo',
        containingFilePath: 'C:/repo/docs/readme.md',
        resourcePath: '/assets/a.png',
      })
    ).toBe('C:/repo/assets/a.png');
  });
});
