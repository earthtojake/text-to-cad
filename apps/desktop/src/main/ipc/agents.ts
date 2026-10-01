/**
 * `agents.*` handlers: the detector, and the pty jobs for install and login.
 *
 * The singletons live here because this is the one place that knows both
 * the agents module and the broadcaster; `ipc/index.ts` spreads
 * `agentsHandlers` into the contract, and main calls `shutdownAgents` on
 * quit.
 */
import { IpcError, broadcast, type IpcContext } from "./register";
import type { IpcHandlers } from "../../shared/ipc";
import type { agentsContract } from "../../shared/ipc/agents";
import { settingsAgentsCache } from "../agents/cache";
import { AgentDetector, PROBE_WAIT_MS } from "../agents/detect";
import { appVersion } from "../app-paths";
import { settings } from "../db/repositories";
import { JobRunner } from "../agents/jobs";
import { startInstall } from "../agents/install";
import { startLogin } from "../agents/auth";
import { agentProvider } from "../agents/registry";
import { spawnJobPty } from "../acp/pty-backend";

// The last launch's table answers a warm launch's first `agents.list` at once
// (`AgentDetector.listWithin`); the probe the window starts replaces it.
export const detector = new AgentDetector(undefined, undefined, settingsAgentsCache(settings, appVersion));
detector.onChange((statuses) => broadcast("agents.status", statuses));

const jobs = new JobRunner(
  spawnJobPty,
  (chunk) => broadcast("agents.output", chunk),
  // An install or a login changes what the next probe finds.
  (job) => void detector.refreshOne(job.agentId).catch((error: unknown) => console.info(`[agents] the re-probe after ${job.kind} failed: ${String(error)}`)),
);

/**
 * How long a cold `agents.list` — one with no cached table — waits for the first probe. The probe starts
 * with the window (`prewarmAgents` in `./acp.ts`), so by the time the renderer
 * asks it is usually done or nearly; this bounds a slow login shell.
 */
export const COLD_LIST_WAIT_MS = PROBE_WAIT_MS;

export const agentsHandlers = {
  agents: {
    list: () => detector.listWithin(COLD_LIST_WAIT_MS),
    refresh: () => detector.refresh(true),

    install: async ({ agentId, platform, index }) => {
      const provider = agentProvider(agentId);
      if (!provider) {
        throw new IpcError(`unknown agent: ${agentId}`);
      }
      const env = await detector.environment();
      try {
        const job = startInstall(jobs, provider, env, { platform, index });
        return { jobId: job.id };
      } catch (error) {
        throw new IpcError(error instanceof Error ? error.message : String(error));
      }
    },

    login: async ({ agentId }) => {
      const provider = agentProvider(agentId);
      if (!provider) {
        throw new IpcError(`unknown agent: ${agentId}`);
      }
      const env = await detector.environment();
      // Not the last launch's row: a CLI installed since has no `binaryPath` there. Past the wait
      // the stale row is all there is, and the login starts from the argv as before.
      const table = (await detector.freshWithin(COLD_LIST_WAIT_MS)) ?? detector.list();
      const status = table.find((candidate) => candidate.id === agentId);
      try {
        const job = startLogin(jobs, provider, status?.binaryPath ?? null, env);
        return { jobId: job.id };
      } catch (error) {
        throw new IpcError(error instanceof Error ? error.message : String(error));
      }
    },

    writeJob: ({ jobId, data }) => {
      jobs.write(jobId, data);
    },

    cancelJob: ({ jobId }) => {
      jobs.cancel(jobId);
    },
  },
} satisfies IpcHandlers<typeof agentsContract, IpcContext>;

export function shutdownAgents() {
  jobs.cancelAll();
}
