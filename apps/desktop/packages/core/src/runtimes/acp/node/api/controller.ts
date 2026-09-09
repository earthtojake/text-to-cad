import { createController } from '@emdash/wire/rpc';
import { acpApiContract } from '#runtimes/acp/api';
import type { AcpRuntime } from '#runtimes/acp/node/runtime/runtime';
import { createAcpProcedures } from './procedures';

export function createAcpController(runtime: AcpRuntime) {
  const procedures = createAcpProcedures(runtime);
  return createController(acpApiContract, {
    ...procedures,
    sessions: runtime.sessionsLiveHost(),
    session: runtime.sessionLiveHost(),
    terminalOutput: (key) => runtime.terminalOutputLog(key.terminalId),
  });
}
