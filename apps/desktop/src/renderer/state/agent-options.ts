import { useMemo } from "react";
import { create } from "zustand";

import {
  defaultModeId,
  effortOption,
  modeChoice,
  modelOption,
  withCurrentValue,
  type ModeChoice,
  type SelectOption,
} from "@shared/acp/options";
import type { AgentOptions } from "@shared/ipc/agent-options";
import type { AgentStatus } from "@shared/agents";

/**
 * What each agent's sessions can be configured with, and what the person
 * chose to start the next one as (`src/shared/ipc/agent-options.ts`).
 *
 * This is what lets the new-session screen show a model, an effort and a
 * mode chip before any agent is running: main remembers every live session's
 * config options and modes against its agent and probes an agent nobody has
 * run yet. An agent with no snapshot contributes nothing — no group in the
 * model menu, no placeholder, no spinner — because a model that cannot be run
 * is not a choice.
 */
type AgentOptionsState = {
  byAgent: Record<string, AgentOptions>;
  ready: boolean;

  load: () => Promise<void>;
  /** Ask main to take a first snapshot of this agent if it has none. */
  probe: (agentId: string, projectId: string | null) => Promise<void>;
  setDefaults: (
    agentId: string,
    defaults: { model?: string | null; effort?: string | null; mode?: string | null },
  ) => Promise<void>;
  receive: (all: AgentOptions[]) => void;
};

const index = (all: AgentOptions[]): Record<string, AgentOptions> =>
  Object.fromEntries(all.map((entry) => [entry.agentId, entry]));

export const useAgentOptions = create<AgentOptionsState>((set) => ({
  byAgent: {},
  ready: false,

  load: async () => {
    set({ byAgent: index(await window.hardcore.agentOptions.list()), ready: true });
  },

  probe: (agentId, projectId) =>
    window.hardcore.agentOptions.probe({ agentId, ...(projectId ? { projectId } : {}) }),

  setDefaults: async (agentId, defaults) => {
    set({ byAgent: index(await window.hardcore.agentOptions.setDefaults({ agentId, ...defaults })) });
  },

  receive: (all) => set({ byAgent: index(all), ready: true }),
}));

/** One provider's model dropdown, as the new-session chips draw it. */
export type ProviderModels = {
  agentId: string;
  agentName: string;
  icon: string | null;
  model: SelectOption;
};

/**
 * The installed agents that have answered, each with its model dropdown and
 * the person's stored choice already applied. Uninstalled agents are not in
 * `agents` at all (the caller passes `useInstalledAgents()`), and an
 * installed one whose probe has not answered has no snapshot, so neither
 * appears.
 */
export function useProviderModels(agents: AgentStatus[]): ProviderModels[] {
  // Selected as the raw record and shaped here rather than inside the
  // selector: each group is a fresh object, and zustand compares what a
  // selector returns — even shallowly — by identity per element, so a
  // selector that builds them re-renders on every store read, for ever.
  const byAgent = useAgentOptions((state) => state.byAgent);
  return useMemo(
    () =>
      agents.flatMap((agent) => {
        const cached = byAgent[agent.id];
        const model = cached ? modelOption(cached.options) : null;
        if (!cached || !model) {
          return [];
        }
        return [
          {
            agentId: agent.id,
            agentName: agent.name,
            icon: agent.icon,
            model: withCurrentValue(model, cached.defaultModel),
          },
        ];
      }),
    [agents, byAgent],
  );
}

/**
 * One agent's effort dropdown, with the stored default applied — null when
 * that agent has no snapshot or the chosen model has no effort levels, which
 * is when the chip is not drawn at all.
 */
export function useProviderEffort(agentId: string | null): SelectOption | null {
  const cached = useAgentOptions((state) => (agentId ? (state.byAgent[agentId] ?? null) : null));
  return useMemo(() => {
    const effort = cached ? effortOption(cached.options) : null;
    return effort && cached ? withCurrentValue(effort, cached.defaultEffort) : null;
  }, [cached]);
}

/**
 * One agent's modes, and the mode the next session with it will start in:
 * the one the person last left it in, else the agent's own auto-approval
 * preset — which is exactly what `SessionManager.create` applies
 * (`main/acp/sessions.ts`), so the chip on the new-session screen shows what
 * is going to happen rather than a guess at it.
 *
 * The source is the snapshot's `modes` when the agent sends any and its
 * `mode` config option otherwise (`shared/acp/options`), so one chip covers
 * both adapters. Null for an agent with no snapshot or one mode: nothing to
 * choose between.
 */
export function useProviderMode(agentId: string | null): ModeChoice | null {
  const cached = useAgentOptions((state) => (agentId ? (state.byAgent[agentId] ?? null) : null));
  return useMemo(() => {
    if (!cached) {
      return null;
    }
    const choice = modeChoice({
      modes: cached.modes,
      configOptions: cached.options,
      currentModeId: null,
    });
    if (!choice) {
      return null;
    }
    const stored = choice.modes.some((mode) => mode.id === cached.defaultMode)
      ? cached.defaultMode
      : null;
    return { ...choice, currentModeId: stored ?? defaultModeId(agentId, choice.modes) ?? choice.currentModeId };
  }, [cached, agentId]);
}
