import { exec } from 'node:child_process';
import { readFile, realpath, stat, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { extname, isAbsolute, join, resolve, sep } from 'node:path';
import type { HostRef } from '@emdash/core/primitives/host/api';
import { parsePortableRelativePath } from '@emdash/core/primitives/path/api';
import type { FsError } from '@emdash/core/runtimes/files/api';
import { err, ok, type Result } from '@emdash/shared';
import type { Disposable } from '@emdash/shared/concurrency';
import { eq } from 'drizzle-orm';
import { app, clipboard, dialog, Menu, shell } from 'electron';
import { nativePathFromHost, resolveRelativePath } from '@core/primitives/desktop-runtime/api';
import {
  getAppById,
  getResolvedLabel,
  OPEN_IN_APPS,
  type OpenInAppId,
  type PlatformConfig,
  type PlatformKey,
} from '@core/primitives/open-in-apps/api/open-in-apps';
import { sshConnections } from '@core/services/app-db/node/schema';
import { getAppDb } from '@main/db/instance';
import type { createDesktopWorkspaceRuntimeAcquirer } from '@main/gateway/workspace-runtime';
import {
  buildRemoteEditorUrl,
  buildRemoteSshCommand,
  buildRemoteTerminalExecArgs,
} from '@main/host/remoteOpenIn';
import { getMainWindow } from '@main/host/window';
import { buildExternalToolEnv } from '@main/lib/childProcessEnv';
import { log } from '@main/lib/logger';
import {
  checkCommand,
  checkMacApp,
  checkMacAppByName,
  checkMacMdfindQuery,
  checkWindowsVisualStudio,
  escapeAppleScriptString,
  execFileCommand,
  listInstalledFontsAll,
  resolveAppVersion,
  resolveWindowsVsProductPath,
  spawnDetachedCommand,
} from './utils';

const FONT_CACHE_TTL_MS = 5 * 60 * 1_000;
const MAX_AUDIO_FILE_BYTES = 20 * 1024 * 1024;

const AUDIO_MIME_TYPES: Record<string, string> = {
  '.aac': 'audio/aac',
  '.flac': 'audio/flac',
  '.m4a': 'audio/mp4',
  '.mp3': 'audio/mpeg',
  '.oga': 'audio/ogg',
  '.ogg': 'audio/ogg',
  '.opus': 'audio/ogg',
  '.wav': 'audio/wav',
  '.webm': 'audio/webm',
};

function expandAbsoluteOrTildePath(rawPath: string): string {
  if (!rawPath || typeof rawPath !== 'string') throw new Error('Invalid path');
  const expanded = rawPath.startsWith('~/') ? join(homedir(), rawPath.slice(2)) : rawPath;
  if (!isAbsolute(expanded)) throw new Error('Path must be absolute or start with ~/');
  return expanded;
}

async function resolveHomeJailedPath(rawPath: string): Promise<string> {
  const expanded = expandAbsoluteOrTildePath(rawPath);
  const realPath = await realpath(expanded);
  const realHome = await realpath(homedir());
  const realHomeWithSep = realHome.endsWith(sep) ? realHome : realHome + sep;
  if (realPath !== realHome && !realPath.startsWith(realHomeWithSep)) {
    throw new Error('Path must be inside the user home directory');
  }
  return realPath;
}

type RemoteTerminalLaunchAttempt = {
  file: string;
  args: string[];
};

type TerminalContextMenuEvent = {
  type: 'terminal-context-menu-action';
  requestId: string;
  action: 'paste' | 'select-all' | 'clear';
};

type WorkspaceRuntimeAcquirer = ReturnType<typeof createDesktopWorkspaceRuntimeAcquirer>;

type ShowWorkspaceItemInFolderError =
  | FsError
  | {
      type: 'not_found';
      entity: 'workspace';
      workspaceId: string;
      message: string;
    }
  | {
      type: 'unsupported_host';
      host: HostRef;
      message: string;
    };

class AppService implements Disposable {
  private cachedAppVersion: string | null = null;
  private cachedAppVersionPromise: Promise<string> | null = null;
  private cachedInstalledFonts: { fonts: string[]; fetchedAt: number } | null = null;
  private emitHostEvent: (event: TerminalContextMenuEvent) => void = () => {};
  private acquireWorkspaceRuntime: WorkspaceRuntimeAcquirer | undefined;

  initialize(options: {
    acquireWorkspaceRuntime: WorkspaceRuntimeAcquirer;
    emitHostEvent(event: TerminalContextMenuEvent): void;
  }): void {
    this.acquireWorkspaceRuntime = options.acquireWorkspaceRuntime;
    this.emitHostEvent = options.emitHostEvent;
    void this.getCachedAppVersion();
  }

  dispose(): void {}

  getCachedAppVersion(): Promise<string> {
    if (this.cachedAppVersion) return Promise.resolve(this.cachedAppVersion);
    if (!this.cachedAppVersionPromise) {
      this.cachedAppVersionPromise = resolveAppVersion().then((version) => {
        this.cachedAppVersion = version;
        return version;
      });
    }
    return this.cachedAppVersionPromise;
  }

  async listInstalledFonts(
    refresh?: boolean
  ): Promise<{ fonts: string[]; cached: boolean; error?: string }> {
    const now = Date.now();
    if (
      !refresh &&
      this.cachedInstalledFonts &&
      now - this.cachedInstalledFonts.fetchedAt < FONT_CACHE_TTL_MS
    ) {
      return { fonts: this.cachedInstalledFonts.fonts, cached: true };
    }
    try {
      const fonts = await listInstalledFontsAll();
      this.cachedInstalledFonts = { fonts, fetchedAt: now };
      return { fonts, cached: false };
    } catch (error) {
      return {
        fonts: this.cachedInstalledFonts?.fonts ?? [],
        cached: Boolean(this.cachedInstalledFonts),
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  async checkInstalledApps(): Promise<Record<string, boolean>> {
    const platform = process.platform as PlatformKey;
    const availability: Record<string, boolean> = {};

    for (const openInApp of Object.values(OPEN_IN_APPS)) {
      const platformConfig = openInApp.platforms[platform];
      if (!platformConfig && !openInApp.alwaysAvailable) {
        availability[openInApp.id] = false;
        continue;
      }
      if (openInApp.alwaysAvailable) {
        availability[openInApp.id] = true;
        continue;
      }
      try {
        let isAvailable = false;
        if (platformConfig?.bundleIds) {
          for (const bundleId of platformConfig.bundleIds) {
            if (await checkMacApp(bundleId)) {
              isAvailable = true;
              break;
            }
          }
        }
        if (!isAvailable && platformConfig?.appNames) {
          for (const appName of platformConfig.appNames) {
            if (await checkMacAppByName(appName)) {
              isAvailable = true;
              break;
            }
          }
        }
        if (!isAvailable && platformConfig?.checkCommands) {
          for (const cmd of platformConfig.checkCommands) {
            if (await checkCommand(cmd)) {
              isAvailable = true;
              break;
            }
          }
        }
        if (!isAvailable && platformConfig?.mdfindQuery && platform === 'darwin') {
          isAvailable = await checkMacMdfindQuery(platformConfig.mdfindQuery);
        }
        if (!isAvailable && platformConfig?.winVswhere && platform === 'win32') {
          isAvailable = await checkWindowsVisualStudio();
        }
        availability[openInApp.id] = isAvailable;
      } catch (error) {
        log.error(`Error checking installed app ${openInApp.id}:`, error);
        availability[openInApp.id] = false;
      }
    }

    return availability;
  }

  async openExternal(url: string): Promise<void> {
    if (!url || typeof url !== 'string') throw new Error('Invalid URL');
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(url);
    } catch {
      throw new Error('Invalid URL format');
    }
    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      throw new Error(
        `Protocol "${parsedUrl.protocol}" is not allowed. Only http and https URLs are permitted.`
      );
    }
    await shell.openExternal(url);
  }

  async openPath(rawPath: string): Promise<void> {
    const realPath = await resolveHomeJailedPath(rawPath);
    const errorMessage = await shell.openPath(realPath);
    if (errorMessage) throw new Error(errorMessage);
  }

  async showWorkspaceItemInFolder(args: {
    workspaceId: string;
    relativePath: string;
  }): Promise<Result<void, ShowWorkspaceItemInFolderError>> {
    const acquireWorkspaceRuntime = this.acquireWorkspaceRuntime;
    if (!acquireWorkspaceRuntime) throw new Error('App service has not been initialized');
    const workspace = await acquireWorkspaceRuntime(args.workspaceId);
    if (!workspace) {
      return err({
        type: 'not_found',
        entity: 'workspace',
        workspaceId: args.workspaceId,
        message: `Workspace not found: ${args.workspaceId}`,
      });
    }
    if (workspace.identity.host.type !== 'local') {
      return err({
        type: 'unsupported_host',
        host: workspace.identity.host,
        message: 'Show in file manager is only available for local workspaces',
      });
    }

    const relativePath = parsePortableRelativePath(args.relativePath, {
      unicodeNormalization: 'preserve',
    });
    if (!relativePath.success) {
      return err({
        type: 'invalid-path',
        path: args.relativePath,
        message: relativePath.error.message,
      });
    }

    const resolved = await workspace.files.client.fs.realPath({
      path: resolveRelativePath(workspace.files.root, relativePath.data),
    });
    if (!resolved.success) return resolved;

    shell.showItemInFolder(nativePathFromHost(resolved.data.path));
    return ok();
  }

  clipboardWriteText(text: string): void {
    if (typeof text !== 'string') throw new Error('Invalid clipboard text');
    clipboard.writeText(text);
  }

  showTerminalContextMenu(args: {
    requestId: string;
    selectionText?: string | null;
    linkText?: string | null;
    x: number;
    y: number;
  }): void {
    if (!args.requestId || typeof args.requestId !== 'string') {
      throw new Error('Invalid context menu request');
    }
    const selectionText = args.selectionText ?? '';
    const linkText = args.linkText?.trim() ?? '';
    const hasSelection = selectionText.length > 0;
    const hasLink = linkText.length > 0;
    const emitAction = (action: 'paste' | 'select-all' | 'clear') => {
      this.emitHostEvent({
        type: 'terminal-context-menu-action',
        requestId: args.requestId,
        action,
      });
    };
    const template: Electron.MenuItemConstructorOptions[] = [
      {
        label: 'Copy',
        accelerator: 'CmdOrCtrl+C',
        enabled: hasSelection,
        click: () => clipboard.writeText(selectionText),
      },
      ...(hasLink
        ? [
            {
              label: 'Copy Link',
              click: () => clipboard.writeText(linkText),
            },
          ]
        : []),
      {
        label: 'Paste',
        accelerator: 'CmdOrCtrl+V',
        click: () => emitAction('paste'),
      },
      { type: 'separator' },
      {
        label: 'Select All',
        accelerator: 'CmdOrCtrl+A',
        click: () => emitAction('select-all'),
      },
      {
        label: 'Clear',
        click: () => emitAction('clear'),
      },
    ];

    Menu.buildFromTemplate(template).popup({
      window: getMainWindow() ?? undefined,
      x: Math.round(args.x),
      y: Math.round(args.y),
    });
  }

  quit(): void {
    app.quit();
  }

  minimizeWindow(): void {
    getMainWindow()?.minimize();
  }

  toggleMaximizeWindow(): void {
    const win = getMainWindow();
    if (!win) return;
    if (win.isMaximized()) {
      win.unmaximize();
    } else {
      win.maximize();
    }
  }

  closeWindow(): void {
    getMainWindow()?.close();
  }

  isWindowMaximized(): boolean {
    return getMainWindow()?.isMaximized() ?? false;
  }

  async openIn(args: {
    app: OpenInAppId;
    path: string;
    isRemote?: boolean;
    sshConnectionId?: string | null;
  }): Promise<void> {
    const { path: target, app: appId, isRemote = false, sshConnectionId } = args;

    if (!target || typeof target !== 'string' || !appId) {
      throw new Error('Invalid arguments');
    }

    const platform = process.platform as PlatformKey;
    const appConfig = getAppById(appId);
    if (!appConfig) throw new Error('Invalid app ID');

    const platformConfig = appConfig.platforms?.[platform];
    const label = getResolvedLabel(appConfig, platform);

    if (!platformConfig && !appConfig.alwaysAvailable) {
      throw new Error(`${label} is not available on this platform.`);
    }

    if (isRemote && sshConnectionId) {
      await this.openInRemote({ appId, appConfig, label, target, platform, sshConnectionId });
      return;
    }

    await this.openInLocal({ appId, label, target, platformConfig });
  }

  private async openInRemote(args: {
    appId: OpenInAppId;
    appConfig: ReturnType<typeof getAppById>;
    label: string;
    target: string;
    platform: PlatformKey;
    sshConnectionId: string;
  }): Promise<void> {
    const { appId, appConfig, label, target, platform, sshConnectionId } = args;

    const [connection] = await getAppDb()
      .select()
      .from(sshConnections)
      .where(eq(sshConnections.id, sshConnectionId))
      .limit(1);

    if (!connection) throw new Error('SSH connection not found');

    const { host, username, port } = connection;

    if (appId === 'vscode' || appId === 'vscodium' || appId === 'cursor' || appId === 'zed') {
      await shell.openExternal(buildRemoteEditorUrl(appId, host, username, target, port));
      return;
    }

    if ((appId === 'terminal' || appId === 'iterm2') && platform === 'darwin') {
      const sshCommand = buildRemoteSshCommand({ host, username, port, targetPath: target });
      const escapedCommand = escapeAppleScriptString(sshCommand);
      const appName = appId === 'terminal' ? 'Terminal' : 'iTerm';
      const script =
        appId === 'terminal'
          ? `tell application "${appName}" to do script "${escapedCommand}"`
          : `tell application "${appName}" to create window with default profile command "${escapedCommand}"`;
      await execFileCommand('osascript', [
        '-e',
        script,
        '-e',
        `tell application "${appName}" to activate`,
      ]);
      return;
    }

    if (appId === 'warp' && platform === 'darwin') {
      const sshCommand = buildRemoteSshCommand({ host, username, port, targetPath: target });
      await shell.openExternal(`warp://action/new_window?cmd=${encodeURIComponent(sshCommand)}`);
      return;
    }

    if (appId === 'ghostty') {
      const remoteExecArgs = buildRemoteTerminalExecArgs({
        host,
        username,
        port,
        targetPath: target,
      });
      const attempts =
        platform === 'darwin'
          ? [
              {
                file: 'open',
                args: ['-n', '-b', 'com.mitchellh.ghostty', '--args', '-e', ...remoteExecArgs],
              },
              { file: 'open', args: ['-na', 'Ghostty', '--args', '-e', ...remoteExecArgs] },
              { file: 'ghostty', args: ['-e', ...remoteExecArgs] },
            ]
          : [{ file: 'ghostty', args: ['-e', ...remoteExecArgs] }];

      await this.launchRemoteTerminal('Ghostty', attempts);
      return;
    }

    if (appId === 'kitty') {
      const remoteExecArgs = buildRemoteTerminalExecArgs({
        host,
        username,
        port,
        targetPath: target,
      });
      const attempts =
        platform === 'darwin'
          ? [
              {
                file: 'open',
                args: ['-n', '-b', 'net.kovidgoyal.kitty', '--args', ...remoteExecArgs],
              },
              { file: 'open', args: ['-na', 'kitty', '--args', ...remoteExecArgs] },
              { file: 'kitty', args: remoteExecArgs },
            ]
          : [{ file: 'kitty', args: remoteExecArgs }];

      await this.launchRemoteTerminal('Kitty', attempts);
      return;
    }

    if (appId === 'alacritty') {
      const remoteExecArgs = buildRemoteTerminalExecArgs({
        host,
        username,
        port,
        targetPath: target,
      });
      const attempts =
        platform === 'darwin'
          ? [
              {
                file: 'open',
                args: ['-n', '-b', 'org.alacritty', '--args', '-e', ...remoteExecArgs],
              },
              { file: 'open', args: ['-na', 'Alacritty', '--args', '-e', ...remoteExecArgs] },
              { file: 'alacritty', args: ['-e', ...remoteExecArgs] },
            ]
          : [{ file: 'alacritty', args: ['-e', ...remoteExecArgs] }];

      await this.launchRemoteTerminal('Alacritty', attempts);
      return;
    }

    if (appId === 'kaku') {
      const remoteExecArgs = buildRemoteTerminalExecArgs({
        host,
        username,
        port,
        targetPath: target,
      });
      const attempts =
        platform === 'darwin'
          ? [
              { file: 'open', args: ['-na', 'Kaku', '--args', 'start', '--', ...remoteExecArgs] },
              { file: 'kaku', args: ['start', '--', ...remoteExecArgs] },
            ]
          : [{ file: 'kaku', args: ['start', '--', ...remoteExecArgs] }];

      await this.launchRemoteTerminal('Kaku', attempts);
      return;
    }

    if (appConfig?.supportsRemote) {
      throw new Error(`Remote SSH not yet implemented for ${label}`);
    }
  }

  private async launchRemoteTerminal(
    label: string,
    attempts: RemoteTerminalLaunchAttempt[]
  ): Promise<void> {
    let lastError: unknown = null;
    for (const attempt of attempts) {
      try {
        await execFileCommand(attempt.file, attempt.args);
        return;
      } catch (error) {
        lastError = error;
      }
    }
    if (lastError instanceof Error) throw lastError;
    throw new Error(`Unable to launch ${label}`);
  }

  private async openInLocal(args: {
    appId: OpenInAppId;
    label: string;
    target: string;
    platformConfig: PlatformConfig | undefined;
  }): Promise<void> {
    const { appId, label, target, platformConfig } = args;

    if (appId === 'finder') {
      const errorMessage = await shell.openPath(target);
      if (errorMessage) throw new Error(errorMessage);
      return;
    }

    if (platformConfig?.winVswhere && process.platform === 'win32') {
      const productPath = await resolveWindowsVsProductPath();
      if (productPath) {
        await spawnDetachedCommand(productPath, [target]);
        return;
      }
      // Fall through to the `devenv {{path}}` openCommands fallback (devenv on PATH).
    }

    if (platformConfig?.openUrls) {
      for (const urlTemplate of platformConfig.openUrls) {
        const url = urlTemplate
          .replace('{{path_url}}', encodeURIComponent(target))
          .replace('{{path}}', target);
        try {
          await shell.openExternal(url);
          return;
        } catch {
          // try next URL
        }
      }
      throw new Error(
        `${label} is not installed or its URI scheme is not registered on this platform.`
      );
    }

    const quoted = (p: string) =>
      process.platform !== 'win32' ? `'${p.replace(/'/g, "'\\''")}'` : `"${p.replace(/"/g, '""')}"`;
    const commands: string[] = platformConfig?.openCommands ?? [];
    const command = commands
      .map((cmd) => cmd.replace('{{path}}', quoted(target)).replace('{{path_raw}}', target))
      .join(' || ');

    if (!command) throw new Error('Unsupported platform or app');

    await new Promise<void>((resolve, reject) => {
      exec(command, { cwd: target, env: buildExternalToolEnv() }, (err) => {
        if (err) return reject(err);
        resolve();
      });
    });
  }

  async openSelectDirectoryDialog(args: {
    title: string;
    message: string;
    defaultPath?: string;
  }): Promise<string | undefined> {
    const result = await dialog.showOpenDialog(getMainWindow()!, {
      title: args.title,
      properties: ['openDirectory'],
      message: args.message,
      defaultPath: args.defaultPath,
    });
    if (result.canceled) return undefined;
    return result.filePaths[0];
  }

  async openSelectAudioFileDialog(args: {
    title: string;
    message: string;
  }): Promise<string | undefined> {
    const result = await dialog.showOpenDialog(getMainWindow()!, {
      title: args.title,
      properties: ['openFile'],
      message: args.message,
      filters: [
        {
          name: 'Audio',
          extensions: ['aac', 'flac', 'm4a', 'mp3', 'oga', 'ogg', 'opus', 'wav', 'webm'],
        },
        { name: 'All files', extensions: ['*'] },
      ],
    });
    if (result.canceled) return undefined;
    return result.filePaths[0];
  }

  async saveTextFile(args: {
    title: string;
    defaultPath: string;
    content: string;
  }): Promise<string | undefined> {
    const result = await dialog.showSaveDialog(getMainWindow()!, {
      title: args.title,
      defaultPath: args.defaultPath,
      filters: [
        { name: 'JSON', extensions: ['json'] },
        { name: 'All files', extensions: ['*'] },
      ],
    });
    if (result.canceled || !result.filePath) return undefined;
    await writeFile(result.filePath, args.content, 'utf8');
    return result.filePath;
  }

  async readAudioFileDataUrl(filePath: string): Promise<string> {
    if (!filePath || typeof filePath !== 'string') throw new Error('Invalid audio path');

    const resolvedPath = await realpath(resolve(filePath));
    const resolvedHome = resolve(homedir());
    const homePrefix = resolvedHome.endsWith(sep) ? resolvedHome : `${resolvedHome}${sep}`;
    if (!resolvedPath.startsWith(homePrefix) && resolvedPath !== resolvedHome) {
      throw new Error('Audio file must be located within the user home directory');
    }

    const extension = extname(filePath).toLowerCase();
    const mimeType = AUDIO_MIME_TYPES[extension];
    if (!mimeType) throw new Error('Unsupported audio file type');

    const fileStat = await stat(resolvedPath);
    if (!fileStat.isFile()) throw new Error('Audio path is not a file');
    if (fileStat.size > MAX_AUDIO_FILE_BYTES) throw new Error('Audio file is larger than 20 MB');

    const file = await readFile(resolvedPath);
    return `data:${mimeType};base64,${file.toString('base64')}`;
  }
}

export const appService = new AppService();
