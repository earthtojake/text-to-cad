import type {
  DependencyId,
  HostDependencySelection,
} from '@emdash/core/primitives/host-dependencies/api';
import type { ProviderCustomConfig } from '@core/primitives/app-settings/api';

export type HostDependencySelectionStore = {
  setSelection(
    hostId: string,
    dependencyId: DependencyId,
    selection: HostDependencySelection
  ): Promise<void>;
};

export function migrateProviderConfigOverrides(
  overrides: Record<string, Partial<ProviderCustomConfig>>
): Record<string, Partial<ProviderCustomConfig>> {
  return overrides;
}

export async function migrateProviderConfigToHostDependencyStore(
  rawOverrides: Record<string, Record<string, unknown>>,
  store: HostDependencySelectionStore
): Promise<void> {
  const migrations: Promise<void>[] = [];

  for (const [providerId, config] of Object.entries(rawOverrides)) {
    const cli = typeof config['cli'] === 'string' ? config['cli'] : undefined;
    const path = typeof config['path'] === 'string' ? config['path'] : undefined;
    const installSource =
      typeof config['installSource'] === 'string' ? config['installSource'] : undefined;

    if (!cli && !path && !installSource) continue;

    let selection: HostDependencySelection = null;
    if (installSource === 'path' && path) {
      selection = { kind: 'path', path };
    } else if (installSource === 'cli' && cli?.startsWith('/')) {
      selection = { kind: 'path', path: cli };
    } else if (path) {
      selection = { kind: 'path', path };
    } else if (cli?.startsWith('/')) {
      selection = { kind: 'path', path: cli };
    }

    if (selection !== null) {
      migrations.push(store.setSelection('local', providerId as DependencyId, selection));
    }
  }

  await Promise.allSettled(migrations);
}
