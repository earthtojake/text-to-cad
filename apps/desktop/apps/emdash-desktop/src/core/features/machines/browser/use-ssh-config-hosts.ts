import { useQuery } from '@tanstack/react-query';
import { getMachinesStore } from '@core/features/machines/contributions/app-stores';

export function useSshConfigHosts() {
  const machines = getMachinesStore();

  return useQuery({
    queryKey: ['ssh-config-hosts'],
    queryFn: () => machines.getSshConfigHosts(),
  });
}

export function useSshConfigHost(alias: string) {
  const machines = getMachinesStore();
  const trimmedAlias = alias.trim();

  return useQuery({
    queryKey: ['ssh-config-host', trimmedAlias],
    queryFn: () => machines.getSshConfigHost(trimmedAlias),
    enabled: trimmedAlias.length > 0,
  });
}
