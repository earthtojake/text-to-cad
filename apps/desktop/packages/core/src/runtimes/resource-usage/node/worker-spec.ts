import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import { resourceUsageComponent } from './component';

type ResourceUsageWorkerOptions = WireComponentWorkerCreateOptions<
  (typeof resourceUsageComponent)['requirements'],
  Record<string, never>
>;

export type ResourceUsageWorkerSpecInput = {
  executable: string;
  env: NodeJS.ProcessEnv;
};

/** Spawn spec for the resource-usage sampling worker. */
export function resourceUsageWorkerSpec(
  input: ResourceUsageWorkerSpecInput
): readonly [typeof resourceUsageComponent, ResourceUsageWorkerOptions] {
  return [
    resourceUsageComponent,
    {
      name: 'resource-usage',
      executable: input.executable,
      env: input.env,
      dependencies: {},
      config: {},
    },
  ];
}
