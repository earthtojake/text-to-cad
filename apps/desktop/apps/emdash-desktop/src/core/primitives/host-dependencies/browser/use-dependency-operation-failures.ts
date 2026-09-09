import type {
  InstallMethod,
  PermissionDeniedError,
} from '@emdash/core/primitives/host-dependencies/api';
import { useCallback, useState } from 'react';

export type DependencyOperationFailure = {
  error: PermissionDeniedError;
  method?: InstallMethod;
};

export function useDependencyOperationFailures() {
  const [failures, setFailures] = useState<Record<string, DependencyOperationFailure>>({});

  const setFailure = useCallback((id: string, failure: DependencyOperationFailure) => {
    setFailures((current) => ({ ...current, [id]: failure }));
  }, []);

  const clearFailure = useCallback((id: string) => {
    setFailures((current) => {
      if (!(id in current)) return current;
      const { [id]: _removed, ...remaining } = current;
      return remaining;
    });
  }, []);

  return { failures, setFailure, clearFailure };
}
