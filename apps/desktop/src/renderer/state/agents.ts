import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import type { AgentJobOutput, AgentStatus } from "@shared/agents";
import { errorMessage } from "@shared/ipc/errors";

/**
 * The agent table — registry rows with what the detector found — and the
 * output of the install and login jobs. A job is in `jobs` from the moment
 * main names it (`seedJob`), not from its first byte, so a screen that
 * remounts finds it running. P6's Agents page reads this; the composer's
 * agent chip reads `installed`.
 */
type AgentsState = {
  agents: AgentStatus[];
  ready: boolean;
  /**
   * Why the agent list could not be read, when it could not. Set only by a
   * failed `load`; any list that arrives afterwards clears it. Shown as its
   * own message, so an unreadable list does not pass for "no agents".
   */
  loadError: string | null;
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

/** The reason for a table every row of which a failed probe flagged, else null. */
const probeFailure = (agents: AgentStatus[]): string | null =>
  agents.length > 0 && agents.every((agent) => agent.probeFailed === true) ? "the check did not finish" : null;

/**
 * The job exists from the moment main names it, not from its first byte: a silent
 * `npm i -g` can sit seconds before printing, and a row remounted in that gap has
 * to find the job running instead of offering a second one. `receiveOutput` merges
 * into this, so an exit chunk that got here first is kept.
 */
function seedJob(
  set: (fn: (state: AgentsState) => Partial<AgentsState>) => void,
  jobId: string,
  agentId: string,
  kind: AgentJobOutput["kind"],
): void {
  set((state) =>
    state.jobs[jobId] ? {} : { jobs: { ...state.jobs, [jobId]: { agentId, kind, output: "", exitCode: null } } },
  );
}

export const useAgents = create<AgentsState>((set) => ({
  agents: [],
  ready: false,
  loadError: null,
  jobs: {},

  /**
   * `ready` means "detection has answered", never "an agent was found".
   *
   * An empty `agents.list` is main's "the first probe is still running",
   * past the wait a cold list allows it (`AgentDetector.listWithin`): the
   * answer follows on `agents.status`, and
   * `receive` marks it — an empty table included. A list that cannot be read
   * at all is an answer too: nothing will follow it, and a screen waiting on
   * `ready` (the welcome's Continue) would otherwise wait forever. That answer
   * is logged and kept in `loadError`, so it reads as a failure, not as an
   * empty table.
   */
  load: async () => {
    try {
      const agents = await window.textToCad.agents.list();
      // A cold probe that failed answers with its flagged rows: nothing follows those on
      // `agents.status`, so they are the answer, and read as the failure they are.
      set({ agents, ready: agents.length > 0, loadError: probeFailure(agents) });
    } catch (error) {
      console.error("[agents] Could not read the agent list (agents.list):", error);
      // The handler's words, without Electron's "Error invoking remote method …" wrapper.
      set({ ready: true, loadError: errorMessage(error) });
    }
  },

  refresh: async () => {
    const agents = await window.textToCad.agents.refresh();
    set({ agents, ready: true, loadError: null });
  },

  install: async (agentId, index = 0) => {
    const { jobId } = await window.textToCad.agents.install({ agentId, index });
    seedJob(set, jobId, agentId, "install");
    return jobId;
  },

  login: async (agentId) => {
    const { jobId } = await window.textToCad.agents.login({ agentId });
    seedJob(set, jobId, agentId, "login");
    return jobId;
  },

  writeJob: (jobId, data) => window.textToCad.agents.writeJob({ jobId, data }),

  cancelJob: (jobId) => window.textToCad.agents.cancelJob({ jobId }),

  // A probe that failed leaves the last launch's rows flagged (`probeFailed`): that is a check
  // that did not happen, so it reads as `loadError` — not as agents that are signed out.
  receive: (agents) =>
    set({ agents, ready: true, loadError: probeFailure(agents) }),

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
 * Whether the table on screen is the last launch's, given before this launch's
 * probe has finished (`AgentStatus.probing`). Its `auth` is provisional: a
 * screen that would say "signed out" waits for `agents.status` instead.
 */
export function useAgentsProbing(): boolean {
  return useAgents((state) => state.agents.some((agent) => agent.probing === true));
}

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
