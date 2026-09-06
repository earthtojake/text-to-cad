/**
 * The Agent Client Protocol: one adapter process per session (plan §4, §5).
 *
 * `connection.ts` spawns the adapter and drives `initialize` / `authenticate`
 * / `session/new` / `session/load` / `session/prompt` / `session/cancel` and
 * the mode and config-option changes; `client.ts` serves the client half
 * (`fs/*`, `terminal/*`, `session/request_permission`) over `terminals.ts`;
 * `sessions.ts` keeps the index in sqlite while the agent keeps the
 * transcript. The pure `session/update` reducer lives in
 * `src/shared/acp/reduce.ts` so the renderer and the tests can run it too.
 *
 * `pty-backend.ts` (node-pty) is imported by main only; everything else runs
 * in plain Node, which is how the CLI harness and the tests use it.
 */
export { SessionConnection, type RecordedFrame, type SessionConnectionOptions } from "./connection";
export { AcpClient, confineToCwd } from "./client";
export { SessionManager, diffCounts, titleFromPrompt, type SessionRepository } from "./sessions";
export {
  DEFAULT_OUTPUT_BYTE_LIMIT,
  TerminalManager,
  type SpawnTerminal,
  type TerminalProcess,
} from "./terminals";
export { spawnProcessTerminal } from "./process-backend";
