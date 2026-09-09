import type { WireComponentWorkerCreateOptions } from '@emdash/wire/worker';
import { hostSettingsComponent } from './component';

type HostSettingsWorkerOptions = WireComponentWorkerCreateOptions<
  (typeof hostSettingsComponent)['requirements'],
  { settingsPath: string }
>;

export type HostSettingsWorkerSpecInput = {
  executable: string;
  env: NodeJS.ProcessEnv;
  /** Absolute path of the host's settings JSON file. */
  settingsPath: string;
};

/** Spawn spec for the host-settings worker. */
export function hostSettingsWorkerSpec(
  input: HostSettingsWorkerSpecInput
): readonly [typeof hostSettingsComponent, HostSettingsWorkerOptions] {
  return [
    hostSettingsComponent,
    {
      name: 'host-settings',
      executable: input.executable,
      env: input.env,
      dependencies: {},
      config: { settingsPath: input.settingsPath },
    },
  ];
}
