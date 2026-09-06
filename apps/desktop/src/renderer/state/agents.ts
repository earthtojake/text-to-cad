import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import type { AgentJobOutput, AgentStatus } from "@shared/agents";

/**
 * The agent table — registry rows with what the detector found — and the
 * output of any install or login job in flight. P6's Agents page reads
 * this; the composer's agent chip reads `installed`.
 */
type AgentsState = {
  agents: AgentStatus[];
  ready: boolean;
  /** Output so far per job id. */
  jobs: Record<string, { agentId: string; kind: AgentJobOutput["kind"]; output: string; exitCode: number | null }>;

  load: () => Promise<void>;
  refresh: () => Promise<void>;
  install: (agentId: string, index?: number) => Promise<string>;
  login: (agentId: string) => Promise<string>;
  writeJob: (jobId: string, data: string) => Promise<void>;
  cancelJob: (jobId: string) => Promise<void>;
  receive: (agents: AgentStatus[]) => void;
  receiveOutput: (chunk: AgentJobOutput) => void;
};

const JOB_TAIL = 64 * 1024;

export const useAgents = create<AgentsState>((set) => ({
  agents: [],
  ready: false,
  jobs: {},

  load: async () => {
    const agents = await window.hardcore.agents.list();
    set({ agents, ready: agents.length > 0 });
  },

  refresh: async () => {
    const agents = await window.hardcore.agents.refresh();
    set({ agents, ready: true });
  },

  install: async (agentId, index = 0) => {
    const { jobId } = await window.hardcore.agents.install({ agentId, index });
    return jobId;
  },

  login: async (agentId) => {
    const { jobId } = await window.hardcore.agents.login({ agentId });
    return jobId;
  },

  writeJob: (jobId, data) => window.hardcore.agents.writeJob({ jobId, data }),

  cancelJob: (jobId) => window.hardcore.agents.cancelJob({ jobId }),

  receive: (agents) => set({ agents, ready: true }),

  receiveOutput: (chunk) =>
    set((state) => {
      const existing = state.jobs[chunk.jobId];
      const output = ((existing?.output ?? "") + chunk.data).slice(-JOB_TAIL);
      return {
        jobs: {
          ...state.jobs,
          [chunk.jobId]: {
            agentId: chunk.agentId,
            kind: chunk.kind,
            output,
            exitCode: chunk.exitCode ?? existing?.exitCode ?? null,
          },
        },
      };
    }),
}));

/**
 * The installed agents, for the composer's agent chip. `useShallow` because
 * the filter builds a fresh array every call and zustand compares with
 * Object.is — without it every render schedules another.
 */
export function useInstalledAgents(): AgentStatus[] {
  return useAgents(
    useShallow((state) => state.agents.filter((agent) => agent.installed || agent.launchWithoutBinary)),
  );
}
