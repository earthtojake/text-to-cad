import { createController, type Controller } from '@emdash/wire/rpc';
import { hostSettingsContract } from '../../api/contract';
import type { HostSettingsRuntime } from '../runtime';

export function createHostSettingsController(runtime: HostSettingsRuntime): Controller {
  return createController(hostSettingsContract, {
    state: runtime.stateHost,
    get: () => runtime.get(),
    update: (input) => runtime.update(input),
  });
}
