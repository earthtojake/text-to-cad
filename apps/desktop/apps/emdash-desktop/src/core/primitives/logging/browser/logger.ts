import {
  isLevelEnabled,
  prepareFields,
  resolveLogLevel,
  type LogLevel,
} from '@emdash/shared/logger';
import type { ContractClient } from '@emdash/wire/rpc';
import { loggingDomain, loggingWireContract } from '@core/primitives/logging/api/wire-contract';
import { domainClient } from '@core/primitives/wire/browser/connection';

type LoggingClient = ContractClient<typeof loggingWireContract>;

const level = resolveLogLevel({ envLevel: import.meta.env.VITE_LOG_LEVEL });

function emit(target: LogLevel, input: unknown[]): void {
  if (target !== 'error' && !isLevelEnabled(target, level)) return;
  // eslint-disable-next-line no-console
  console[target](...input);
  forwardToHost(target, input);
}

/** Fire-and-forget: logging must never throw or block, even before the wire is seeded. */
function forwardToHost(target: LogLevel, input: unknown[]): void {
  try {
    void domainClient<LoggingClient>(loggingDomain, loggingWireContract)
      .then((client) =>
        client.writeRendererLog({
          level: target,
          source: 'renderer',
          input: input.map((value) => prepareFields(value)),
        })
      )
      .catch(() => undefined);
  } catch {
    // Wire not seeded yet (early bootstrap, tests): console output already happened.
  }
}

export const log = {
  level,
  debug: (...input: unknown[]) => emit('debug', input),
  info: (...input: unknown[]) => emit('info', input),
  warn: (...input: unknown[]) => emit('warn', input),
  error: (...input: unknown[]) => emit('error', input),
};
