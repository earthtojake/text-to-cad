import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import {
  lifecycleScriptsDomain,
  lifecycleScriptsWireContract,
} from '../lifecycle-scripts-wire-contract';
import {
  projectSettingsContract,
  projectSettingsDomain,
  projectWorkspacesContract,
  projectWorkspacesDomain,
} from '../project-contracts';
import { workspaceRegistryDomain, workspaceRegistryWireContract } from '../registry-wire-contract';
import { workspacesDomain, workspacesWireContract } from '../wire-contract';

export type WorkspacesWireClient = ContractClient<typeof workspacesWireContract>;

export function getWorkspacesWireClient(): Promise<WorkspacesWireClient> {
  return domainClient<WorkspacesWireClient>(workspacesDomain, workspacesWireContract);
}

export type WorkspaceRegistryWireClient = ContractClient<typeof workspaceRegistryWireContract>;

export function getWorkspaceRegistryWireClient(): Promise<WorkspaceRegistryWireClient> {
  return domainClient<WorkspaceRegistryWireClient>(
    workspaceRegistryDomain,
    workspaceRegistryWireContract
  );
}

export type ProjectWorkspacesClient = ContractClient<typeof projectWorkspacesContract>;

export function getProjectWorkspacesClient(): Promise<ProjectWorkspacesClient> {
  return domainClient<ProjectWorkspacesClient>(projectWorkspacesDomain, projectWorkspacesContract);
}

export type ProjectSettingsClient = ContractClient<typeof projectSettingsContract>;

export function getProjectSettingsClient(): Promise<ProjectSettingsClient> {
  return domainClient<ProjectSettingsClient>(projectSettingsDomain, projectSettingsContract);
}

export type LifecycleScriptsClient = ContractClient<typeof lifecycleScriptsWireContract>;

export function getLifecycleScriptsClient(): Promise<LifecycleScriptsClient> {
  return domainClient<LifecycleScriptsClient>(lifecycleScriptsDomain, lifecycleScriptsWireContract);
}
