/**
 * Agent registry, detection, installation and auth (plan §5).
 *
 * `registry.ts` is the provider table; `detect.ts` probes PATH against a
 * login-shell environment resolved once (`shell-env.ts`); `install.ts` and
 * `auth.ts` run their jobs through `jobs.ts` in a pty. Nothing here spawns
 * an agent — that is `../acp`.
 */
export { AGENT_PROVIDERS, agentProvider } from "./registry";
export { AgentDetector, nodeProbes, parseVersion, which, type DetectorProbes } from "./detect";
export { loginEnv, parseEnv, processEnv, stripHostSession, type Env } from "./shell-env";
export { JobRunner, type Job, type JobPty, type SpawnJobPty } from "./jobs";
export { currentPlatform, installCommand, startInstall } from "./install";
export { loginCommand, startLogin } from "./auth";
