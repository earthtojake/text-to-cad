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
import { AgentDetector } from "../agents/detect";
import { JobRunner } from "../agents/jobs";
import { startInstall } from "../agents/install";
import { startLogin } from "../agents/auth";
import { agentProvider } from "../agents/registry";
import { spawnJobPty } from "../acp/pty-backend";

export const detector = new AgentDetector();
detector.onChange((statuses) => broadcast("agents.status", statuses));

const jobs = new JobRunner(
  spawnJobPty,
  (chunk) => broadcast("agents.output", chunk),
  // An install or a login changes what the next probe finds.
  (job) => void detector.refreshOne(job.agentId),
);

export const agentsHandlers = {
  agents: {
    list: () => detector.list(),
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
      const status = detector.list().find((candidate) => candidate.id === agentId);
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
