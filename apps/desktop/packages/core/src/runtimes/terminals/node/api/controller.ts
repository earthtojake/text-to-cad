import { createController } from '@emdash/wire/rpc';
import { terminalsContract } from '#runtimes/terminals/api';
import type { TerminalsRuntime } from '#runtimes/terminals/node/runtime/runtime';

export function createTerminalsController(runtime: TerminalsRuntime) {
  return createController(terminalsContract, {
    start: (input) => runtime.start(input),
    getShellAvailability: () => runtime.getShellAvailability(),
    output: (key) => runtime.outputLog(key),
    sessions: runtime.sessionsHost,
    sendInput: ({ key, data }) => runtime.sendInput(key, data),
    resize: ({ key, cols, rows }) => runtime.resize(key, cols, rows),
    kill: ({ key }) => runtime.kill(key),
    killTmuxSessions: (input) => runtime.killTmuxSessions(input),
  });
}
