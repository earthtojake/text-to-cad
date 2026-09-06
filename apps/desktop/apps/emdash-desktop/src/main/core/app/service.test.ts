import { LOCAL_HOST_REF, hostRef } from '@emdash/core/primitives/host/api';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { hostPathFromNative } from '@core/primitives/desktop-runtime/api';

const mocks = vi.hoisted(() => ({
  exec: vi.fn(),
  getVersion: vi.fn(() => '1.1.27'),
  openExternal: vi.fn(),
  openPath: vi.fn(),
  showItemInFolder: vi.fn(),
  workspaceGet: vi.fn(),
  filesRealPath: vi.fn(),
  menuPopup: vi.fn(),
  menuBuildFromTemplate: vi.fn((template: Electron.MenuItemConstructorOptions[]) => ({
    popup: mocks.menuPopup,
    template,
  })),
  eventEmit: vi.fn(),
  clipboardWriteText: vi.fn(),
}));

vi.mock('node:child_process', () => ({
  exec: mocks.exec,
}));

vi.mock('electron', () => ({
  app: {
    getAppPath: vi.fn(() => ''),
    getVersion: mocks.getVersion,
    quit: vi.fn(),
  },
  clipboard: {
    writeText: mocks.clipboardWriteText,
  },
  dialog: {
    showOpenDialog: vi.fn(),
  },
  shell: {
    openExternal: mocks.openExternal,
    openPath: mocks.openPath,
    showItemInFolder: mocks.showItemInFolder,
  },
  Menu: {
    buildFromTemplate: mocks.menuBuildFromTemplate,
  },
}));

vi.mock('@main/host/window', () => ({
  getMainWindow: vi.fn(),
}));

vi.mock('@main/gateway/workspace-runtime', () => ({
  acquireDesktopWorkspaceRuntime: (workspaceId: string) => mocks.workspaceGet(workspaceId),
}));

vi.mock('@core/services/app-db/node/schema', () => ({
  sshConnections: {},
}));

vi.mock('@main/host/events', () => ({
  events: {
    emit: mocks.eventEmit,
    on: vi.fn(() => vi.fn()),
  },
}));

vi.mock('@main/lib/logger', () => ({
  log: {
    error: vi.fn(),
  },
}));

vi.mock('@main/lib/childProcessEnv', () => ({
  buildExternalToolEnv: () => ({}),
}));

const { appService } = await import('./service');
appService.initialize({
  acquireWorkspaceRuntime: mocks.workspaceGet,
  emitHostEvent: mocks.eventEmit,
});

const originalPlatform = Object.getOwnPropertyDescriptor(process, 'platform');

function setPlatform(platform: NodeJS.Platform): void {
  Object.defineProperty(process, 'platform', {
    ...originalPlatform,
    value: platform,
  });
}

describe('AppService.openIn', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setPlatform('win32');
    mocks.openPath.mockResolvedValue('');
    mocks.exec.mockImplementation(
      (_command: string, _options: object, callback: (error: Error | null) => void) => {
        callback(null);
      }
    );
  });

  afterEach(() => {
    if (originalPlatform) Object.defineProperty(process, 'platform', originalPlatform);
  });

  it('opens the platform file manager with Electron shell.openPath instead of a shell command', async () => {
    const target = 'C:/Users/Qwenzy/Desktop/ees_ams';

    await appService.openIn({ app: 'finder', path: target });

    expect(mocks.openPath).toHaveBeenCalledWith(target);
    expect(mocks.exec).not.toHaveBeenCalled();
  });

  it('throws when Electron shell.openPath returns an error message', async () => {
    const target = 'C:/Users/Qwenzy/Desktop/missing';
    mocks.openPath.mockResolvedValueOnce('Path does not exist');

    await expect(appService.openIn({ app: 'finder', path: target })).rejects.toThrow(
      'Path does not exist'
    );
    expect(mocks.openPath).toHaveBeenCalledWith(target);
    expect(mocks.exec).not.toHaveBeenCalled();
  });
});

describe('AppService.showWorkspaceItemInFolder', () => {
  const workspaceRoot = hostPathFromNative('/workspace');

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.workspaceGet.mockReturnValue({
      identity: { host: LOCAL_HOST_REF },
      files: {
        root: workspaceRoot,
        client: { fs: { realPath: mocks.filesRealPath } },
      },
      release: vi.fn(),
    });
  });

  it('resolves and reveals a path through the workspace files runtime', async () => {
    const resolvedPath = hostPathFromNative('/workspace/reports/summary.md');
    mocks.filesRealPath.mockResolvedValue({ success: true, data: { path: resolvedPath } });

    const result = await appService.showWorkspaceItemInFolder({
      workspaceId: 'workspace-1',
      relativePath: 'reports/summary.md',
    });

    expect(result).toEqual({ success: true, data: undefined });
    expect(mocks.workspaceGet).toHaveBeenCalledWith('workspace-1');
    expect(mocks.filesRealPath).toHaveBeenCalledWith({
      path: hostPathFromNative('/workspace/reports/summary.md'),
    });
    expect(mocks.showItemInFolder).toHaveBeenCalledWith('/workspace/reports/summary.md');
  });

  it('returns a typed error for paths that are not relative to the workspace', async () => {
    const result = await appService.showWorkspaceItemInFolder({
      workspaceId: 'workspace-1',
      relativePath: '/etc/passwd',
    });

    expect(result).toEqual({
      success: false,
      error: {
        type: 'invalid-path',
        path: '/etc/passwd',
        message: 'Path must be relative',
      },
    });
    expect(mocks.filesRealPath).not.toHaveBeenCalled();
    expect(mocks.showItemInFolder).not.toHaveBeenCalled();
  });

  it('does not reveal paths rejected by the workspace files runtime', async () => {
    mocks.filesRealPath.mockResolvedValue({
      success: false,
      error: {
        type: 'invalid-path',
        path: 'outside-link',
        message: 'Path resolves outside the workspace root',
      },
    });

    const result = await appService.showWorkspaceItemInFolder({
      workspaceId: 'workspace-1',
      relativePath: 'outside-link',
    });

    expect(result).toEqual({
      success: false,
      error: {
        type: 'invalid-path',
        path: 'outside-link',
        message: 'Path resolves outside the workspace root',
      },
    });
    expect(mocks.showItemInFolder).not.toHaveBeenCalled();
  });

  it('returns a typed error when the workspace is unavailable', async () => {
    mocks.workspaceGet.mockReturnValue(undefined);

    const result = await appService.showWorkspaceItemInFolder({
      workspaceId: 'missing-workspace',
      relativePath: 'reports/summary.md',
    });

    expect(result).toEqual({
      success: false,
      error: {
        type: 'not_found',
        entity: 'workspace',
        workspaceId: 'missing-workspace',
        message: 'Workspace not found: missing-workspace',
      },
    });
    expect(mocks.filesRealPath).not.toHaveBeenCalled();
    expect(mocks.showItemInFolder).not.toHaveBeenCalled();
  });

  it('returns a typed error without resolving paths for a remote workspace', async () => {
    const remoteHost = hostRef('remote', 'ssh-connection-1');
    mocks.workspaceGet.mockReturnValue({
      identity: { host: remoteHost },
      files: {
        root: workspaceRoot,
        client: { fs: { realPath: mocks.filesRealPath } },
      },
      release: vi.fn(),
    });

    const result = await appService.showWorkspaceItemInFolder({
      workspaceId: 'remote-workspace',
      relativePath: 'reports/summary.md',
    });

    expect(result).toEqual({
      success: false,
      error: {
        type: 'unsupported_host',
        host: remoteHost,
        message: 'Show in file manager is only available for local workspaces',
      },
    });
    expect(mocks.filesRealPath).not.toHaveBeenCalled();
    expect(mocks.showItemInFolder).not.toHaveBeenCalled();
  });

  it('throws unexpected Electron shell failures', async () => {
    const resolvedPath = hostPathFromNative('/workspace/reports/summary.md');
    mocks.filesRealPath.mockResolvedValue({ success: true, data: { path: resolvedPath } });
    mocks.showItemInFolder.mockImplementationOnce(() => {
      throw new Error('Electron shell unavailable');
    });

    await expect(
      appService.showWorkspaceItemInFolder({
        workspaceId: 'workspace-1',
        relativePath: 'reports/summary.md',
      })
    ).rejects.toThrow('Electron shell unavailable');
  });
});

describe('AppService.showTerminalContextMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('copies the exact selected terminal text without trimming whitespace', () => {
    appService.showTerminalContextMenu({
      requestId: 'request-1',
      selectionText: '  indented value\n',
      x: 10,
      y: 20,
    });

    const template = mocks.menuBuildFromTemplate.mock.calls[0]?.[0];
    const copyItem = template?.find((item) => item.label === 'Copy');

    expect(copyItem?.enabled).toBe(true);
    copyItem?.click?.({} as Electron.MenuItem, undefined as never, undefined as never);

    expect(mocks.clipboardWriteText).toHaveBeenCalledWith('  indented value\n');
  });

  it('allows copying whitespace-only selections', () => {
    appService.showTerminalContextMenu({
      requestId: 'request-1',
      selectionText: '   ',
      x: 10,
      y: 20,
    });

    const template = mocks.menuBuildFromTemplate.mock.calls[0]?.[0];
    const copyItem = template?.find((item) => item.label === 'Copy');

    expect(copyItem?.enabled).toBe(true);
    copyItem?.click?.({} as Electron.MenuItem, undefined as never, undefined as never);

    expect(mocks.clipboardWriteText).toHaveBeenCalledWith('   ');
  });
});
