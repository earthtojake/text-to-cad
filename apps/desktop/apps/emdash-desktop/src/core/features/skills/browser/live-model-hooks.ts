import type { HostRef } from '@emdash/core/primitives/host/api';
import type { CatalogSkill } from '@emdash/core/primitives/skills/api';
import { remote, type RemoteModel } from '@emdash/wire/state';
import { useMemo } from 'react';
import { useRemoteModelState } from '@core/primitives/wire/browser/use-remote-model-state';
import { skillsContract } from '../api';
import { getSkillsClient } from './client';

let installedRemotePromise: Promise<RemoteModel<typeof skillsContract.installed>> | undefined;

export function useInstalledSkillsLiveModel(host: HostRef): {
  data: CatalogSkill[];
  isLoading: boolean;
} {
  const key = useMemo(() => ({ host }), [host]);
  const state = useRemoteModelState(skillsContract.installed, getInstalledRemote, key, 'list', {
    initialValue: [],
  });

  return { data: state.value ?? [], isLoading: state.isLoading };
}

function getInstalledRemote(): Promise<RemoteModel<typeof skillsContract.installed>> {
  installedRemotePromise ??= getSkillsClient().then((client) =>
    remote(skillsContract.installed, client.installed, { lingerMs: 15_000 })
  );
  return installedRemotePromise;
}

export async function resetInstalledSkillsLiveModelForTests(): Promise<void> {
  const remoteModel = await installedRemotePromise;
  installedRemotePromise = undefined;
  await remoteModel?.dispose();
}
