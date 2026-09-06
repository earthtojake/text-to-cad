import { app, clipboard, Menu, shell } from 'electron';
import { desktopHostEvents } from '@core/features/workbench/node';
import { MENU_ITEMS } from '@core/manifests/shared/menu-items';
import {
  resolveEffectiveChord,
  toElectronAccelerator,
  type PlatformContext,
} from '@core/primitives/keybindings/api';
import {
  HARDCORE_DOCS_URL,
  HARDCORE_ISSUES_NEW_URL,
  HARDCORE_RELEASES_URL,
} from '@core/primitives/urls/api/urls';
import { telemetryService } from '@main/lib/telemetry';

export interface MenuKeybindingSnapshotEntry {
  readonly commandId: string;
  readonly title: string;
  readonly accelerator: string | null;
}

const platformContext: PlatformContext = {
  os: process.platform === 'darwin' ? 'mac' : process.platform === 'win32' ? 'windows' : 'linux',
};
let currentKeybindings: readonly MenuKeybindingSnapshotEntry[] = MENU_ITEMS.map((command) => {
  const chord = command.keybinding
    ? resolveEffectiveChord(command.keybinding, {}, platformContext)
    : null;
  return {
    commandId: command.id,
    title: command.title,
    accelerator: chord ? toElectronAccelerator(chord) : null,
  };
});

function emitCommand(commandId: string): void {
  desktopHostEvents.emit(undefined, { type: 'menu-command', commandId });
}

function copyInstallationId(): void {
  const instanceId = telemetryService.getInstanceId() ?? 'unavailable';
  const lines = [
    `Hardcore ${app.getVersion()}`,
    `Installation ID: ${instanceId}`,
    `Platform: ${process.platform} ${process.arch}`,
    `Electron: ${process.versions.electron}`,
  ];
  clipboard.writeText(lines.join('\n'));
}

export function setupApplicationMenu(
  snapshot: readonly MenuKeybindingSnapshotEntry[] = currentKeybindings
): void {
  currentKeybindings = snapshot;
  const isMac = process.platform === 'darwin';
  const acceleratorFor = (commandId: string) =>
    snapshot.find((entry) => entry.commandId === commandId)?.accelerator ?? undefined;

  const template: Electron.MenuItemConstructorOptions[] = [
    // macOS app menu
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              {
                label: `About ${app.name}`,
                click: () => app.showAboutPanel(),
              },
              { type: 'separator' as const },
              {
                label: 'Settings\u2026',
                accelerator: acceleratorFor('app.settings'),
                click: () => emitCommand('app.settings'),
              },
              {
                label: 'Check for Updates\u2026',
                click: () => desktopHostEvents.emit(undefined, { type: 'menu-check-for-updates' }),
              },
              { type: 'separator' as const },
              { role: 'services' as const },
              { type: 'separator' as const },
              { role: 'hide' as const },
              { role: 'hideOthers' as const },
              { role: 'unhide' as const },
              { type: 'separator' as const },
              {
                label: `Quit ${app.name}`,
                accelerator: 'CmdOrCtrl+Q',
                click: () => app.quit(),
              },
            ],
          } as Electron.MenuItemConstructorOptions,
        ]
      : []),
    // File menu
    {
      label: 'File',
      submenu: [
        // On non-macOS, put Settings in File menu
        ...(!isMac
          ? [
              {
                label: 'Settings\u2026',
                accelerator: acceleratorFor('app.settings'),
                click: () => emitCommand('app.settings'),
              },
              { type: 'separator' as const },
            ]
          : []),
        isMac
          ? {
              label: 'Close Tab',
              accelerator: acceleratorFor('workbench.tabClose'),
              click: () => emitCommand('workbench.tabClose'),
            }
          : {
              label: 'Quit',
              accelerator: 'CmdOrCtrl+Q',
              click: () => app.quit(),
            },
      ],
    },
    // Edit menu
    {
      label: 'Edit',
      submenu: [
        {
          label: 'Undo',
          accelerator: 'CmdOrCtrl+Z',
          click: () => desktopHostEvents.emit(undefined, { type: 'menu-undo' }),
        },
        {
          label: 'Redo',
          accelerator: isMac ? 'Shift+CmdOrCtrl+Z' : 'CmdOrCtrl+Y',
          click: () => desktopHostEvents.emit(undefined, { type: 'menu-redo' }),
        },
        { type: 'separator' as const },
        { role: 'cut' as const },
        { role: 'copy' as const },
        { role: 'paste' as const },
        ...(isMac ? [{ role: 'pasteAndMatchStyle' as const }] : []),
        { role: 'delete' as const },
        { role: 'selectAll' as const },
      ],
    },
    // View menu
    {
      label: 'View',
      submenu: [
        { role: 'reload' as const },
        { role: 'forceReload' as const },
        { role: 'toggleDevTools' as const },
        { type: 'separator' as const },
        {
          label: 'Command Palette\u2026',
          accelerator: acceleratorFor('app.commandPalette'),
          click: () => emitCommand('app.commandPalette'),
        },
        { type: 'separator' as const },
        { role: 'resetZoom' as const },
        { role: 'zoomIn' as const },
        { role: 'zoomOut' as const },
        { type: 'separator' as const },
        { role: 'togglefullscreen' as const },
      ],
    },
    // Window menu
    { role: 'windowMenu' as const },
    // Help menu
    {
      role: 'help' as const,
      label: 'Help',
      submenu: [
        ...(!isMac
          ? [
              {
                label: 'Check for Updates\u2026',
                click: () => desktopHostEvents.emit(undefined, { type: 'menu-check-for-updates' }),
              },
              { type: 'separator' as const },
            ]
          : []),
        {
          label: 'Docs',
          click: () => {
            void shell.openExternal(HARDCORE_DOCS_URL);
          },
        },
        {
          label: 'Changelog',
          click: () => {
            void shell.openExternal(HARDCORE_RELEASES_URL);
          },
        },
        { type: 'separator' as const },
        {
          label: 'Troubleshooting',
          submenu: [
            {
              label: 'Report Issue\u2026',
              click: () => {
                void shell.openExternal(HARDCORE_ISSUES_NEW_URL);
              },
            },
            {
              label: 'Copy Installation ID',
              click: copyInstallationId,
            },
          ],
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

export function setApplicationMenuKeybindings(
  snapshot: readonly MenuKeybindingSnapshotEntry[]
): void {
  setupApplicationMenu(snapshot);
}
