import { createController, type Controller } from '@emdash/wire/rpc';
import { scriptsContract } from '../../api/contract';
import type { ScriptsRuntime } from '../runtime';

export function createScriptsController(runtime: ScriptsRuntime): Controller {
  return createController(scriptsContract, {
    runs: runtime.runsHost,
    output: (key) => runtime.outputLog(key),
    start: (input) => runtime.start(input),
    wait: (input) => runtime.wait(input),
    stop: (input) => runtime.stop(input),
    sendInput: (input) => runtime.sendInput(input),
    resize: (input) => runtime.resize(input),
  });
}
