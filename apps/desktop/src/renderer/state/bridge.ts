/**
 * One place where main's pushes land in the stores.
 *
 * Components subscribe to stores, never to IPC. That keeps the event listeners
 * out of React's lifecycle — a `projects.changed` listener mounted per row
 * would be re-registered on every render of the sidebar — and it means a
 * change made from the app menu updates the same state a click would.
 */
import type { IpcEventPayload } from "@shared/ipc";

import { useAcp } from "./acp";
import { useAgents } from "./agents";
import { useComposer } from "./composer";
import { useExplorer } from "./explorer";
import { usePlugins } from "./plugins";
import { useProjects } from "./projects";
import { useRuntime } from "./runtime";
import { useSessions } from "./sessions";
import { useSettings } from "./settings";
import { useUi } from "./ui";
import { useUpdates } from "./updates";

export type UiCommand = IpcEventPayload<"ui.command">["command"];

/**
 * A `ui.command`, whether it came from the app menu, a shortcut bound in the
 * renderer, or a control on the page (the files-changed pill sends
 * `open-review`). One switch, so none of them can drift.
 */
export function runUiCommand(command: UiCommand): void {
  const ui = useUi.getState();
  switch (command) {
    case "open-settings":
      ui.openSettings();
      break;
    case "close-settings":
      ui.closeSettings();
      break;
    case "command-palette":
      ui.toggleCommandPalette();
      break;
    case "toggle-sidebar":
      void toggleLayout("sidebarCollapsed");
      break;
    case "toggle-explorer":
      void toggleLayout("explorerCollapsed");
      break;
    case "new-session":
      useSessions.getState().setActive(null);
      ui.closeSettings();
      break;
    case "open-review": {
      // P3 gives the tab a body; opening it (and the explorer, if it was
      // collapsed) is the whole of what the pill asks for.
      const { settings, setLayout } = useSettings.getState();
      if (settings?.layout.explorerCollapsed) {
        void setLayout({ explorerCollapsed: false });
      }
      const explorer = useExplorer.getState();
      const existing = explorer.tabs.find((tab) => tab.kind === "review");
      if (existing) {
        explorer.setActive(existing.id);
      } else {
        explorer.open("review");
      }
      break;
    }
  }
}

/** Attach every main → renderer listener. Returns a detach function. */
export function subscribeToMain(): () => void {
  const off = [
    window.hardcore.on("projects.changed", (projects) => {
      useProjects.getState().receive(projects);
    }),
    window.hardcore.on("sessions.changed", (sessions) => {
      useSessions.getState().receive(sessions);
    }),
    window.hardcore.on("settings.changed", (settings) => {
      useSettings.getState().receive(settings);
    }),
    window.hardcore.on("app.updateStatus", (status) => {
      useUpdates.getState().receive(status);
    }),
    window.hardcore.on("session.state", ({ sessionId, state }) => {
      useAcp.getState().receiveState(sessionId, state);
    }),
    window.hardcore.on("session.update", ({ sessionId, event }) => {
      useAcp.getState().receiveEvent(sessionId, event);
      // A turn that just ended frees the session for the next queued prompt.
      if (event.type === "prompt/end") {
        void useComposer.getState().drain(sessionId);
      }
    }),
    window.hardcore.on("terminal.output", ({ sessionId, terminalId, data }) => {
      useAcp.getState().receiveTerminalOutput(sessionId, terminalId, data);
    }),
    window.hardcore.on("agents.status", (agents) => {
      useAgents.getState().receive(agents);
    }),
    window.hardcore.on("agents.output", (chunk) => {
      useAgents.getState().receiveOutput(chunk);
    }),
    window.hardcore.on("plugins.status", (statuses) => {
      usePlugins.getState().receive(statuses);
    }),
    window.hardcore.on("runtime.progress", ({ status, message, percent }) => {
      useRuntime.getState().receive(status, message, percent);
    }),
    window.hardcore.on("files.changed", ({ projectId, changes }) => {
      useExplorer.getState().receiveChanges(
        projectId,
        changes.map((change) => change.path),
      );
    }),
    window.hardcore.on("ui.command", ({ command }) => {
      runUiCommand(command);
    }),
  ];

  // The explorer strip belongs to the active project, so it follows the
  // project selection rather than being loaded once. Subscribing to the store
  // rather than doing this in a component keeps the load off React's
  // lifecycle — a remount must not re-read the strip and lose the selection.
  let boundProject: string | null | undefined;
  const unsubscribeProjects = useProjects.subscribe((state) => {
    if (state.activeId === boundProject) {
      return;
    }
    boundProject = state.activeId;
    void useExplorer.getState().bindProject(state.activeId);
  });

  return () => {
    unsubscribeProjects();
    for (const detach of off) {
      detach();
    }
  };
}

function toggleLayout(key: "sidebarCollapsed" | "explorerCollapsed") {
  const { settings, setLayout } = useSettings.getState();
  if (!settings) {
    return Promise.resolve();
  }
  return setLayout({ [key]: !settings.layout[key] });
}

/** First read of everything the shell needs. */
export async function hydrate(): Promise<void> {
  await Promise.all([
    useSettings.getState().load(),
    useProjects.getState().load(),
    useSessions.getState().load(),
    useUpdates.getState().load(),
    useAgents.getState().load(),
  ]);
  // The explorer's strip follows the active project, which the subscription
  // in `subscribeToMain` picks up as soon as `useProjects.load` resolves.
  await useExplorer.getState().bindProject(useProjects.getState().activeId);
}
