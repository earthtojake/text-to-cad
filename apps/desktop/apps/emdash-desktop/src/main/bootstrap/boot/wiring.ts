import { provisionWorkspaceErrorToWorkspaceError } from '@core/features/workspaces/node/wire-controller';
import type { DesktopControllerContext } from '@core/manifests/node/controllers';
import { appOperations } from '@main/core/app/controller';
import {
  createDependencyManagerResolver,
  ensureAgentDependenciesProbed,
} from '@main/core/dependencies/dependency-managers';
import { getTerminalColorEnv } from '@main/core/terminal-shell/color-env';
import { withCompensation } from '@main/core/utils/compensation';
import type { DesktopRuntimes } from '@main/gateway/desktop-runtimes';
import { setBrowserCorsRelaxationSettings } from '@main/host/browser/browser-profile-session';
import { browserWebContentsRegistry } from '@main/host/browser/browser-webcontents-registry';
import { browserOperations } from '@main/host/browser/controller';
import { writeRendererLogEntry } from '@main/host/file-logger';
import { updateOperations } from '@main/host/updates/controller-operations';
import { applyNativeTheme } from '@main/host/window';
import { log } from '@main/lib/logger';
import { telemetryService } from '@main/lib/telemetry';
import type { DatabaseBundle } from './phases/database';
import type { ServicesBundle } from './phases/services';

export type DesktopControllerOptions = Omit<
  DesktopControllerContext,
  'hosts' | 'runtimes' | 'scope' | 'ssh'
>;

export function createDesktopWireOptions(
  database: DatabaseBundle,
  services: ServicesBundle,
  runtimes: DesktopRuntimes
): DesktopControllerOptions {
  const taskService = services.taskService;
  const github = services.github;
  const getDependencyManager = createDependencyManagerResolver(runtimes.clients.hostDependencies);
  return {
    agentDependencies: {
      ensureAgentDependenciesProbed,
      getDependencyManager,
    },
    appSettings: database.appSettings,
    browserOperations,
    compensation: withCompensation,
    db: database.db,
    editorBuffer: database.editorBuffer,
    github: {
      accountService: github.account,
      deviceFlowService: github.deviceFlow,
      repositoryService: github.repositories,
    },
    gitCredentials: services.gitCredentials,
    hostAvailability: runtimes.hostAvailability,
    hostOperations: {
      openExternal: ({ url }) => appOperations.openExternal(url),
      openPath: ({ path }) => appOperations.openPath(path),
      showWorkspaceItemInFolder: (input) => appOperations.showWorkspaceItemInFolder(input),
      clipboardWriteText: ({ text }) => appOperations.clipboardWriteText(text),
      persistDroppedBlob: (input) => appOperations.persistDroppedBlob(input),
      persistClipboardImage: () => appOperations.persistClipboardImage(),
      showTerminalContextMenu: (input) => appOperations.showTerminalContextMenu(input),
      setMenuKeybindings: (input) => appOperations.setMenuKeybindings(input),
      quit: () => appOperations.quit(),
      resolveQuitConfirmation: (input) => appOperations.resolveQuitConfirmation(input),
      ackShutdownFlush: () => appOperations.ackShutdownFlush(),
      shutdownReady: () => appOperations.shutdownReady(),
      openIn: (input) => appOperations.openIn(input),
      checkInstalledApps: () => appOperations.checkInstalledApps(),
      listInstalledFonts: (input) => appOperations.listInstalledFonts(input),
      openSelectDirectoryDialog: (input) => appOperations.openSelectDirectoryDialog(input),
      openSelectAudioFileDialog: (input) => appOperations.openSelectAudioFileDialog(input),
      saveTextFile: (input) => appOperations.saveTextFile(input),
      readAudioFileDataUrl: ({ filePath }) => appOperations.readAudioFileDataUrl(filePath),
      minimizeWindow: () => appOperations.minimizeWindow(),
      toggleMaximizeWindow: () => appOperations.toggleMaximizeWindow(),
      closeWindow: () => appOperations.closeWindow(),
      isWindowMaximized: () => appOperations.isWindowMaximized(),
      getAppVersion: () => appOperations.getAppVersion(),
      getElectronVersion: () => appOperations.getElectronVersion(),
      getPlatform: () => appOperations.getPlatform(),
      getPlatformDisplayName: () => appOperations.getPlatformDisplayName(),
      getDiagnosticLogAttachment: () => appOperations.getDiagnosticLogAttachment(),
      submitFeedback: (input) => appOperations.submitFeedback(input),
    },
    hostIsReachable: services.hostIsReachable,
    logger: log,
    loggingOperations: {
      writeRendererLog: (input) => writeRendererLogEntry(input),
    },
    notifications: services.notifications,
    projectDeletion: services.projectDeletion,
    promptLibrary: services.promptLibrary,
    projects: services.projects,
    projectSettings: services.projectSettings,
    providerSettings: services.providerSettings,
    reconcileSweep: services.reconcileSweep,
    search: services.search,
    runtimeClients: {
      getMementosRuntimeClient: async () => runtimes.clients.mementos,
      getPullRequestsRuntimeClient: async () => runtimes.clients.pullRequests,
    },
    settingsRuntime: {
      setKeyboardSettings: (settings) => browserWebContentsRegistry.setKeyboardSettings(settings),
      setBrowserSettings: setBrowserCorsRelaxationSettings,
      setTheme: applyNativeTheme,
    },
    telemetry: telemetryService,
    taskService,
    taskSessions: services.taskSessions,
    terminalShell: {
      getColorEnv: getTerminalColorEnv,
    },
    updateOperations,
    workspaceIdentity: database.workspaceIdentity,
    workspacePlacement: services.workspacePlacement,
    workspaces: {
      async provisionTask(taskId, signal) {
        const result = await taskService.provisionWorkspace(taskId, signal);
        return result.success
          ? result
          : { success: false, error: provisionWorkspaceErrorToWorkspaceError(result.error) };
      },
      reprovisionWorkspace: (workspaceId, options) =>
        taskService.reprovisionWorkspace(workspaceId, options),
    },
  };
}
