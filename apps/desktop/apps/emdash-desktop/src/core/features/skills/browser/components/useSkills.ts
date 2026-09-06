import type { HostRef } from '@emdash/core/primitives/host/api';
import { mergeSkillsInstalledState, type CatalogIndex } from '@emdash/core/primitives/skills/api';
import { useToast } from '@emdash/ui/react/primitives';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';
import { getCatalogClient } from '@core/features/catalog/api/browser/client';
import { log } from '@core/primitives/logging/browser/logger';
import { useDebounce } from '@core/primitives/react-hooks/browser/useDebounce';
import { captureTelemetry } from '@core/primitives/telemetry/browser/telemetry-client';
import { getSkillsClient } from '../client';
import { useInstalledSkillsLiveModel } from '../live-model-hooks';

const CATALOG_QUERY_KEY = ['skills', 'catalog'] as const;

export function useSkills({ host, searchQuery = '' }: { host: HostRef; searchQuery?: string }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data: installedLiveSkills, isLoading: isLoadingInstalled } =
    useInstalledSkillsLiveModel(host);

  const { data: rawCatalog = null, isPending: isLoadingCatalog } = useQuery({
    queryKey: CATALOG_QUERY_KEY,
    queryFn: async () => {
      const client = await getCatalogClient();
      const result = await client.getSkillsCatalog(undefined);
      if (result.success) return result.data;
      throw new Error(result.error.message);
    },
  });

  const catalog = useMemo(
    () => (rawCatalog ? mergeSkillsInstalledState(rawCatalog, installedLiveSkills) : null),
    [rawCatalog, installedLiveSkills]
  );
  const isLoading = isLoadingCatalog || isLoadingInstalled;

  const refreshMutation = useMutation({
    mutationFn: async () => {
      const client = await getCatalogClient();
      const result = await client.refreshSkillsCatalog(undefined);
      if (result.success) return result.data;
      throw new Error(result.error.message);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(CATALOG_QUERY_KEY, data);
    },
    onError: (error) => {
      log.error('Failed to refresh catalog:', error);
    },
  });

  const refresh = useCallback(() => refreshMutation.mutate(), [refreshMutation]);

  const installMutation = useMutation({
    mutationFn: async (skillId: string) => {
      const catalogClient = await getCatalogClient();
      const payload = await catalogClient.resolveSkillInstall({ skillId });
      if (!payload.success) throw new Error(payload.error.message);
      const skillsClient = await getSkillsClient();
      const result = await skillsClient.install({ host, skill: payload.data });
      if (!result.success) throw new Error(result.error.message);
      return skillId;
    },
    onError: (error) => {
      toast.error('Install failed', { description: error.message });
    },
    onSuccess: (skillId) => {
      const skill = queryClient
        .getQueryData<CatalogIndex>(CATALOG_QUERY_KEY)
        ?.skills.find((s) => s.id === skillId);

      captureTelemetry('skill_installed', { source: skill?.source });
      toast('Skill installed', { description: `${skillId} is now available across your agents` });
      void queryClient.invalidateQueries({ queryKey: ['skills', 'skillssh-search'] });
      queryClient.removeQueries({ queryKey: ['skills', 'detail'] });
    },
  });

  const install = useCallback(
    async (skillId: string): Promise<boolean> => {
      try {
        await installMutation.mutateAsync(skillId);
        return true;
      } catch {
        return false;
      }
    },
    [installMutation]
  );

  const uninstallMutation = useMutation({
    mutationFn: async (skillId: string) => {
      const skill =
        catalog?.skills.find((candidate) => candidate.id === skillId) ??
        installedLiveSkills.find(
          (candidate) => candidate.id === skillId || candidate.installId === skillId
        );
      const name = skill?.installId ?? skillId;
      const skillsClient = await getSkillsClient();
      const result = await skillsClient.remove({ host, name });
      if (!result.success) throw new Error(result.error.message);
      return skillId;
    },
    onError: (error) => {
      toast.error('Uninstall failed', { description: error.message });
    },
    onSuccess: () => {
      captureTelemetry('skill_uninstalled');

      toast('Skill removed', { description: 'Skill has been uninstalled' });
      void queryClient.invalidateQueries({ queryKey: ['skills', 'skillssh-search'] });
      queryClient.removeQueries({ queryKey: ['skills', 'detail'] });
    },
  });

  const uninstall = useCallback(
    async (skillId: string): Promise<boolean> => {
      try {
        await uninstallMutation.mutateAsync(skillId);
        return true;
      } catch {
        return false;
      }
    },
    [uninstallMutation]
  );

  const skillShQuery = useDebounce(searchQuery.trim(), 300);
  const { data: skillShSkills = [], isFetching: isSearchingSkillSh } = useQuery({
    queryKey: ['skills', 'skillssh-search', skillShQuery],
    queryFn: async () => {
      const client = await getCatalogClient();
      const result = await client.searchSkillSh({ query: skillShQuery });
      if (result.success) return result.data;
      throw new Error(result.error.message);
    },
    enabled: skillShQuery.length >= 2,
    staleTime: 60_000,
  });

  const mergedSkillShSkills = useMemo(() => {
    const index: CatalogIndex = {
      version: rawCatalog?.version ?? 0,
      lastUpdated: rawCatalog?.lastUpdated ?? new Date(0).toISOString(),
      skills: skillShSkills,
    };
    return mergeSkillsInstalledState(index, installedLiveSkills).skills;
  }, [rawCatalog, skillShSkills, installedLiveSkills]);

  const filteredSkills = useMemo(() => {
    if (!catalog) return [];
    const q = searchQuery.toLowerCase().trim();
    if (!q) return catalog.skills;
    return catalog.skills.filter(
      (s) =>
        s.displayName.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        s.id.toLowerCase().includes(q)
    );
  }, [catalog, searchQuery]);

  const installedSkills = useMemo(
    () => filteredSkills.filter((s) => s.installed),
    [filteredSkills]
  );

  const recommendedSkills = useMemo(
    () => filteredSkills.filter((s) => !s.installed),
    [filteredSkills]
  );

  const skillShSearchSkills = useMemo(() => {
    const installedKeys = new Set<string>();
    for (const skill of catalog?.skills ?? []) {
      if (!skill.installed) continue;
      installedKeys.add(skill.id);
      if (skill.installId) installedKeys.add(skill.installId);
    }

    return mergedSkillShSkills.filter(
      (skill) =>
        !skill.installed &&
        !installedKeys.has(skill.id) &&
        (!skill.installId || !installedKeys.has(skill.installId))
    );
  }, [catalog, mergedSkillShSkills]);

  return {
    catalog,
    isLoading,
    isRefreshing: refreshMutation.isPending,
    searchQuery,
    filteredSkills,
    installedSkills,
    recommendedSkills,
    skillShSearchSkills,
    isSearchingSkillSh,
    refresh,
    install,
    uninstall,
  };
}

export type UseSkillsResult = ReturnType<typeof useSkills>;
