import { isDeepEqual } from '@emdash/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  APP_SETTINGS_STALE_TIME_MS,
  type AppSettingsMeta,
  appSettingsMetaQueryKey,
  getAllAppSettingsFromCache,
  getAppSettingValueSnapshot,
  invalidateAppSettingsKey,
  mergeAppSettingsValue,
  prefetchAppSettingsKey,
  requestAppSettingsMeta,
  resetAppSettingsFieldRequest,
  resetAppSettingsRequest,
  restoreAppSettingsCache,
  setAppSettingsValueInCache,
  updateAppSettingsRequest,
} from '@core/features/settings/api/browser/app-settings-client';
import type { AppSettings, AppSettingsKey } from '@core/services/settings/api';

export { getAppSettingValueSnapshot, prefetchAppSettingsKey };

export function useAppSettingsKey<K extends AppSettingsKey>(key: K) {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<AppSettingsMeta<K>>({
    queryKey: appSettingsMetaQueryKey(key),
    queryFn: () => requestAppSettingsMeta(key),
    staleTime: APP_SETTINGS_STALE_TIME_MS,
  });

  const updateMutation = useMutation<
    void,
    Error,
    Partial<AppSettings[K]>,
    { prev: AppSettingsMeta<K> | undefined; prevAll: AppSettings | undefined }
  >({
    mutationFn: (partial) => {
      const current = queryClient.getQueryData<AppSettingsMeta<K>>(appSettingsMetaQueryKey(key));
      const merged = mergeAppSettingsValue(current?.value, partial);
      return updateAppSettingsRequest(key, merged);
    },
    onMutate: async (partial) => {
      await queryClient.cancelQueries({ queryKey: appSettingsMetaQueryKey(key) });
      const prev = queryClient.getQueryData<AppSettingsMeta<K>>(appSettingsMetaQueryKey(key));
      const prevAll = getAllAppSettingsFromCache();
      const merged = mergeAppSettingsValue(prev?.value, partial);
      setAppSettingsValueInCache(key, merged);
      return { prev, prevAll };
    },
    onError: (_err, _partial, ctx) => {
      if (ctx) restoreAppSettingsCache(key, ctx.prev, ctx.prevAll);
      invalidateAppSettingsKey(key);
    },
    onSettled: () => {
      invalidateAppSettingsKey(key);
    },
  });

  const resetMutation = useMutation<void, Error, void>({
    mutationFn: () => resetAppSettingsRequest(key),
    onSuccess: () => {
      invalidateAppSettingsKey(key);
    },
  });

  const resetFieldMutation = useMutation<void, Error, keyof AppSettings[K]>({
    mutationFn: (field) => resetAppSettingsFieldRequest(key, field),
    onSuccess: () => {
      invalidateAppSettingsKey(key);
    },
  });

  return {
    value: data?.value,
    defaults: data?.defaults,
    overrides: data?.overrides,
    isLoading,
    isSaving: updateMutation.isPending || resetMutation.isPending || resetFieldMutation.isPending,
    isOverridden: data ? !isDeepEqual(data.value, data.defaults) : false,
    isFieldOverridden: (field: keyof AppSettings[K]) => !!(data && field in data.overrides),
    update: updateMutation.mutate,
    updateAsync: updateMutation.mutateAsync,
    reset: resetMutation.mutate,
    resetField: (field: keyof AppSettings[K]) => resetFieldMutation.mutate(field),
  };
}
