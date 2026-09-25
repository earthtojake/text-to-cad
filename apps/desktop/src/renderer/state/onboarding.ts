import { create } from "zustand";

import { useAgents } from "@renderer/state/agents";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";

/**
 * The first-run flow: the welcome that opens once, and the sidebar's
 * Getting started checklist after it.
 *
 * What the person has done lives in settings (`onboarding*`); this store only
 * holds whether this run shows onboarding at all, which main decides (off
 * under the test suites — `src/main/onboarding.ts`).
 */
type OnboardingState = {
  /** Null until main has answered. */
  enabled: boolean | null;
  load: () => Promise<void>;
};

export const useOnboarding = create<OnboardingState>((set) => ({
  enabled: null,
  load: async () => {
    const { enabled } = await window.hardcore.onboarding.status();
    set({ enabled });
  },
}));

/** The agents onboarding offers; the rest are in Settings › Agents. */
export const ONBOARDING_AGENT_IDS = ["claude-code", "codex"] as const;

/** Whether the welcome should cover the window right now. */
export function useShowWelcome(): boolean {
  const enabled = useOnboarding((state) => state.enabled);
  const completed = useSettings((state) => state.settings?.onboardingCompleted);
  return enabled === true && completed === false;
}

export type ChecklistItem = { id: "agent" | "folder" | "session" | "viewer"; label: string; done: boolean };

/** The checklist's items, each ticked by what the person has actually done. */
export function useChecklist(): ChecklistItem[] {
  const agentReady = useAgents((state) =>
    state.agents.some((agent) => agent.installed && (agent.auth === "authenticated" || agent.auth === "not-required")),
  );
  const hasSession = useSessions((state) => state.sessions.some((session) => !session.archived));
  const hasFolder = useProjects((state) => state.draft !== null || state.activeId !== null);
  const viewerOpened = useSettings((state) => state.settings?.onboardingViewerOpened ?? false);
  return [
    { id: "agent", label: "Connect an agent", done: agentReady },
    { id: "folder", label: "Open a folder", done: hasFolder || hasSession },
    { id: "session", label: "Ask for your first part", done: hasSession },
    { id: "viewer", label: "Open a part in the viewer", done: viewerOpened },
  ];
}

/** Whether the checklist belongs in the sidebar right now. */
export function useShowChecklist(): boolean {
  const enabled = useOnboarding((state) => state.enabled);
  const settings = useSettings((state) => state.settings);
  return enabled === true && settings !== null && settings.onboardingCompleted && !settings.onboardingChecklistDismissed;
}

/** Ticks the checklist's last item the first time a CAD file reaches the viewer. */
export function markViewerOpened(): void {
  const { settings, patch } = useSettings.getState();
  if (settings && !settings.onboardingViewerOpened) {
    void patch({ onboardingViewerOpened: true });
  }
}
