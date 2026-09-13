import type {
  HostSettings,
  HostSettingsState,
  UpdateHostSettingsInput,
} from '@emdash/core/runtimes/host-settings/api';
import { remote, type RemoteModel } from '@emdash/wire/state';
import { useCallback, useMemo } from 'react';
import { machinesContract } from '@core/features/machines/api';
import { getMachinesClient } from '@core/features/machines/api/browser/client';
import { useRemoteModelState } from '@core/primitives/wire/browser/use-remote-model-state';

let hostSettingsRemotePromise:
  | Promise<RemoteModel<typeof machinesContract.hostSettings>>
  | undefined;

export type HostSettingsViewState = {
  settings: HostSettings | undefined;
  /** True when the settings file exists but did not parse; defaults are in effect. */
  parseError: boolean;
  isLoading: boolean;
  error: Error | null;
  /** Partial write; null clears a field. The fresh state streams back through the model. */
  update: (patch: UpdateHostSettingsInput) => Promise<void>;
};

/**
 * Observes the per-host defaults (host-settings runtime) through the machines
 * domain. The live model also reflects out-of-band edits to the settings file,
 * so external changes appear without a reload.
 */
export function useHostSettings(
  machineId: string | undefined,
  enabled: boolean
): HostSettingsViewState {
  const modelKey = useMemo(() => ({ machineId }), [machineId]);
  const modelState = useRemoteModelState(
    machinesContract.hostSettings,
    getHostSettingsRemote,
    modelKey,
    'current',
    { enabled }
  );

  const update = useCallback(
    async (patch: UpdateHostSettingsInput) => {
      const client = await getMachinesClient();
      const result = await client.updateHostSettings({ machineId, patch });
      if (!result.success) throw new Error(result.error.message, { cause: result.error });
    },
    [machineId]
  );

  const state: HostSettingsState | undefined = modelState.value;
  return {
    settings: state?.settings,
    parseError: state?.parseError ?? false,
    isLoading: enabled && modelState.isLoading,
    error: toError(modelState.error),
    update,
  };
}

function getHostSettingsRemote(): Promise<RemoteModel<typeof machinesContract.hostSettings>> {
  hostSettingsRemotePromise ??= getMachinesClient().then((client) =>
    remote(machinesContract.hostSettings, client.hostSettings, { lingerMs: 15_000 })
  );
  return hostSettingsRemotePromise;
}

function toError(error: unknown): Error | null {
  if (error === undefined) return null;
  return error instanceof Error ? error : new Error(String(error));
}
