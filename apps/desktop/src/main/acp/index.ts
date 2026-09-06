/**
 * The Agent Client Protocol: one adapter process per session. **Filled by P1.**
 *
 * `connection.ts` spawns the adapter and drives `initialize` / `authenticate`
 * / `session/new` / `session/prompt` / `session/cancel`; `client.ts` serves the
 * client half (`fs/*`, `terminal/*`, `session/request_permission`);
 * `sessions.ts` keeps the index in sqlite while the agent keeps the transcript.
 * The pure `session/update` reducer lives in `src/shared/acp/reduce.ts` so the
 * renderer and the tests can both run it.
 */
export {};
