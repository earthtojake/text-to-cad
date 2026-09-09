import {
  RECOMMENDED_CORE_DEPENDENCIES,
  REQUIRED_CORE_DEPENDENCIES,
  type HostDependencySnapshot,
  type HostDependencyView,
} from '@emdash/core/services/host-dependencies/api';
import type { MachineSystemDependencyStatus } from './contract';

const requiredCoreDependencyIds = new Set(
  REQUIRED_CORE_DEPENDENCIES.map((definition) => definition.id)
);
const recommendedCoreDependencyIds = new Set(
  RECOMMENDED_CORE_DEPENDENCIES.map((definition) => definition.id)
);
const systemDependencyOrder = [...REQUIRED_CORE_DEPENDENCIES, ...RECOMMENDED_CORE_DEPENDENCIES].map(
  (definition) => definition.id
);

export const systemDependencyIds = new Set(systemDependencyOrder);

export function mapSystemDependencySnapshot(
  snapshot: HostDependencySnapshot
): MachineSystemDependencyStatus[] {
  const dependencies = snapshot.dependencies;
  return systemDependencyOrder
    .map((id) => dependencies[id])
    .filter((view): view is HostDependencyView => !!view)
    .map(mapSystemDependencyView);
}

export function mapSystemDependencyView(view: HostDependencyView): MachineSystemDependencyStatus {
  return {
    id: view.definition.id,
    name: view.definition.name,
    tier: systemDependencyTier(view.definition.id),
    status: view.status,
    path: view.resolved?.path ?? null,
    ...(view.definition.installDocs ? { installDocs: view.definition.installDocs } : {}),
    installOptions: view.installOptions,
  };
}

function systemDependencyTier(id: string): MachineSystemDependencyStatus['tier'] {
  if (requiredCoreDependencyIds.has(id)) return 'required';
  if (recommendedCoreDependencyIds.has(id)) return 'recommended';
  return 'recommended';
}
