import type {
  ProvidedWireComponentRequirements,
  WireComponentWorkerCreateOptions,
} from '@emdash/wire/worker';
import type { z } from 'zod';
import { terminalsComponent, type terminalsComponentConfigSchema } from './component';

type TerminalsConfig = z.infer<typeof terminalsComponentConfigSchema>;
type TerminalsWorkerOptions = WireComponentWorkerCreateOptions<
  (typeof terminalsComponent)['requirements'],
  TerminalsConfig
>;

export type TerminalsWorkerSpecInput = {
  executable: string;
  env: NodeJS.ProcessEnv;
  userEnv: ProvidedWireComponentRequirements<
    (typeof terminalsComponent)['requirements']
  >['userEnv'];
  /**
   * Genuinely per-app policy: the desktop keeps terminals alive for the app's
   * lifetime, while a detachable server reaps terminals nobody is attached to.
   */
  lifecycle: NonNullable<TerminalsConfig['lifecycle']>;
};

/** Spawn spec for the terminals runtime worker. */
export function terminalsWorkerSpec(
  input: TerminalsWorkerSpecInput
): readonly [typeof terminalsComponent, TerminalsWorkerOptions] {
  return [
    terminalsComponent,
    {
      name: 'terminals',
      executable: input.executable,
      env: input.env,
      dependencies: { userEnv: input.userEnv },
      config: { lifecycle: input.lifecycle },
    },
  ];
}
