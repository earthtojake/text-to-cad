/**
 * One place where main's pushes land in the stores.
 *
 * Components subscribe to stores, never to IPC. That keeps the event listeners
 * out of React's lifecycle — a `projects.changed` listener mounted per row
 * would be re-registered on every render of the sidebar — and it means a
 * change made from the app menu updates the same state a click would.
 */
import { useAcp } from "./acp";
import { useAgents } from "./agents";
import { useExplorer } from "./explorer";
import { usePlugins } from "./plugins";
import { useProjects } from "./projects";
import { useRuntime } from "./runtime";
import { useSessions } from "./sessions";
import { useSettings } from "./settings";
import { useUi } from "./ui";
import { useUpdates } from "./updates";

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
    window.hardcore.on("ui.command", ({ command }) => {
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
          // P1 owns session creation. Until then the menu item lands on the
          // new-session state the session pane already shows.
          useSessions.getState().setActive(null);
          useUi.getState().closeSettings();
          break;
      }
    }),
  ];

  return () => {
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
  // Nothing to hydrate for the explorer yet — the strip is in-memory until P3
  // persists it. Named here so the omission is a decision, not an oversight.
  void useExplorer;
}
