import type { HostSettings, HostSettingsContract } from '@emdash/core/runtimes/host-settings/api';
import { log } from '@emdash/shared/logger';
import type { ContractClient } from '@emdash/wire/rpc';

export type HostSettingsReader = Pick<ContractClient<HostSettingsContract>, 'get'>;

/**
 * The per-host defaults from the host-settings runtime (shellSetup, worktree root,
 * tmux), used as fallbacks under per-project or per-workspace overrides. A failed
 * read degrades to "no defaults" rather than blocking the caller.
 */
export async function hostSettingsDefaults(
  hostSettings: HostSettingsReader
): Promise<HostSettings> {
  const state = await hostSettings.get();
  if (!state.success) {
    log.warn('Could not read host settings; continuing without host defaults', {
      error: state.error,
    });
    return {};
  }
  return state.data.settings;
}
