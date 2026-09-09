import { createController, type Controller } from '@emdash/wire/rpc';
import { workspaceRegistryContract } from '../../api/contract';
import type { WorkspaceRegistryRuntime } from '../runtime';

export function createWorkspaceRegistryController(runtime: WorkspaceRegistryRuntime): Controller {
  return createController(workspaceRegistryContract, {
    records: runtime.recordsHost,
    projectConfig: runtime.projectConfigHost,
    getProjectConfig: (input) => runtime.getProjectConfig(input),
    refreshProjectConfig: (input) => runtime.refreshProjectConfig(input),
    patchPersonalProjectConfig: (input) => runtime.patchPersonalProjectConfig(input),
    importLegacyLifecycleSettings: (input) => runtime.importLegacyLifecycleSettings(input),
    activateWorkspace: (input) => runtime.activateWorkspace(input),
    createWorkspace: (input) => runtime.createWorkspace(input),
    createWorktree: (input) => runtime.createWorktree(input),
    deactivateWorkspace: (input) => runtime.deactivateWorkspace(input),
    deleteWorkspace: (input) => runtime.deleteWorkspace(input),
    deleteWorktree: (input) => runtime.deleteWorktree(input),
    measureUsage: (input, meta) => runtime.measureUsage(input, meta.signal),
    refresh: (input) => runtime.refresh(input),
    retryStep: (input) => runtime.retryStep(input),
    runScript: (input) => runtime.runScript(input),
    updateWorktree: (input) => runtime.updateWorktree(input),
  });
}
