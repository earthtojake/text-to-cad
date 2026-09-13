import { LiveLogSource } from '@emdash/wire/live';
import { createController, defineContract, liveLog, type Controller } from '@emdash/wire/rpc';
import { z } from 'zod';

export const api = defineContract({
  buildLog: liveLog({ key: z.object({ buildId: z.string() }) }),
});

// One authoritative log source per build id; the resolver hands the source to
// the wire so attached clients receive resets and appends as live updates.
const logs = new Map<string, LiveLogSource>();

function logFor(buildId: string): LiveLogSource {
  let source = logs.get(buildId);
  if (!source) {
    source = new LiveLogSource({ maxBufferBytes: 64 });
    logs.set(buildId, source);
  }
  return source;
}

export function appendLine(buildId: string, line: string): void {
  logFor(buildId).append(`${line}\n`);
}

export function createLogController(): Controller {
  return createController(api, {
    buildLog: ({ buildId }) => logFor(buildId),
  });
}
