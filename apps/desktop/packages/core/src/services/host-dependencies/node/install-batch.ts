import { err } from '@emdash/shared';
import type {
  DependencyId,
  ElevationPolicy,
  HostDependencyDefinition,
  InstallCommandOption,
} from '#primitives/host-dependencies/api';
import type {
  HostDependencyInstallBatchResult,
  HostDependencyInstallRequest,
} from '#services/host-dependencies/api';
import { installOptionsForPlatform, selectInstallOption } from './install-execution';

export type ResolvedBatchRequest = {
  request: HostDependencyInstallRequest;
  option: InstallCommandOption;
};

export type InstallBatchPlan = {
  /** Requests that failed to resolve to an installable option. */
  errors: HostDependencyInstallBatchResult;
  /** Apt requests with package metadata, merged into a single transaction. */
  aptBatch: ResolvedBatchRequest[];
  /** Remaining requests, installed one at a time in request order. */
  sequential: ResolvedBatchRequest[];
};

export function planInstallBatch(
  requests: HostDependencyInstallRequest[],
  getDefinition: (id: DependencyId) => HostDependencyDefinition | undefined
): InstallBatchPlan {
  const plan: InstallBatchPlan = { errors: {}, aptBatch: [], sequential: [] };
  for (const request of requests) {
    const definition = getDefinition(request.id);
    if (!definition) {
      plan.errors[request.id] = err({ type: 'unknown-dependency', id: request.id });
      continue;
    }
    const option = selectInstallOption(installOptionsForPlatform(definition), request.method);
    if (!option) {
      plan.errors[request.id] = err({ type: 'no-install-command', id: request.id });
      continue;
    }
    const resolved: ResolvedBatchRequest = { request, option };
    if (option.method === 'apt' && (option.packages?.length ?? 0) > 0) {
      plan.aptBatch.push(resolved);
    } else {
      plan.sequential.push(resolved);
    }
  }
  return plan;
}

/**
 * A merged apt transaction runs as one command, so the group shares a single elevation
 * decision: elevated whenever any member requires or requested it.
 */
export function aptBatchElevation(requests: ResolvedBatchRequest[]): {
  policy: ElevationPolicy;
  elevate: boolean;
} {
  const policies = requests.map(({ option }) => option.elevation ?? 'never');
  const policy: ElevationPolicy = policies.includes('always')
    ? 'always'
    : policies.includes('on-failure')
      ? 'on-failure'
      : 'never';
  return { policy, elevate: requests.some(({ request }) => request.elevate === true) };
}

export function aptBatchPackages(requests: ResolvedBatchRequest[]): string[] {
  return [...new Set(requests.flatMap(({ option }) => option.packages ?? []))];
}
