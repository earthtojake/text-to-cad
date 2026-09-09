import type { PromptLibraryService } from '@core/features/library/node/prompt-library-service';
import type { WorkspaceIdentityService } from '@core/features/workspaces/api/node/workspace-identity-service';
import type { NotificationService } from '@core/services/notifications/node';
import type { AppSettingsService } from '@core/services/settings/node';
import type { ProviderOverrideSettings } from '@core/services/settings/node/provider-settings-service';

type CoreServiceInstances = {
  appSettings: AppSettingsService;
  notifications: NotificationService;
  promptLibrary: PromptLibraryService;
  providerSettings: ProviderOverrideSettings;
};

let coreServices: CoreServiceInstances | undefined;
let workspaceIdentity: WorkspaceIdentityService | undefined;

export function setCoreServiceInstances(instances: CoreServiceInstances): void {
  if (coreServices) throw new Error('Core services are already initialized');
  coreServices = instances;
}

export function setWorkspaceIdentityService(service: WorkspaceIdentityService): void {
  if (workspaceIdentity) throw new Error('Workspace identity service is already initialized');
  workspaceIdentity = service;
}

export function getAppSettingsService(): AppSettingsService {
  return requireCoreServices().appSettings;
}

export function getNotificationService(): NotificationService {
  return requireCoreServices().notifications;
}

export function getPromptLibraryService(): PromptLibraryService {
  return requireCoreServices().promptLibrary;
}

export function getProviderOverrideSettings(): ProviderOverrideSettings {
  return requireCoreServices().providerSettings;
}

export function getWorkspaceIdentityService(): WorkspaceIdentityService {
  if (!workspaceIdentity) {
    throw new Error('Workspace identity service has not been initialized');
  }
  return workspaceIdentity;
}

export function disposeNotificationService(): void {
  coreServices?.notifications.dispose();
}

export function resetCoreServiceInstancesForTests(): void {
  coreServices = undefined;
  workspaceIdentity = undefined;
}

function requireCoreServices(): CoreServiceInstances {
  if (!coreServices) throw new Error('Core services have not been initialized');
  return coreServices;
}
