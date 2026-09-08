import { create } from "zustand";

/**
 * The Settings pages, in the order the plan lists them (§10) — minus CAD
 * Runtime: the runtime ships inside the app, and what is left to say about
 * it is a status block on About & Updates.
 */
export const SETTINGS_SECTIONS = [
  "general",
  "agents",
  "appearance",
  "git",
  "shortcuts",
  "about",
] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

/** Nav labels, in one place so the nav, the palette and the header agree. */
export const SETTINGS_SECTION_LABELS: Record<SettingsSection, string> = {
  general: "General",
  agents: "Agents",
  appearance: "Appearance",
  git: "Git & Worktrees",
  shortcuts: "Keyboard shortcuts",
  about: "About & Updates",
};

/**
 * Window-level UI state: which of the two full-window routes is showing, and
 * whether the command palette is up.
 *
 * Settings is a route, not a dialog — it replaces the whole window, Codex-style
 * (plan §3). Keeping that as a route rather than a modal is what lets it have
 * its own nav and its own search without fighting the shell for the keyboard.
 */
type UiState = {
  route: "app" | "settings";
  settingsSection: SettingsSection;
  commandPaletteOpen: boolean;
  /**
   * What is in the palette's box.
   *
   * The palette has no filter of its own beyond that box — every row carries
   * a `value` and cmdk scores the query against it. One way to narrow the
   * list, and it is the one the person can see the shape of.
   */
  commandPaletteQuery: string;

  openSettings: (section?: SettingsSection) => void;
  closeSettings: () => void;
  setSettingsSection: (section: SettingsSection) => void;
  setCommandPaletteOpen: (open: boolean) => void;
  toggleCommandPalette: () => void;
  setCommandPaletteQuery: (query: string) => void;
};

export const useUi = create<UiState>((set) => ({
  route: "app",
  settingsSection: "general",
  commandPaletteOpen: false,
  commandPaletteQuery: "",

  openSettings: (section) =>
    set((state) => ({
      route: "settings",
      settingsSection: section ?? state.settingsSection,
      commandPaletteOpen: false,
    })),
  closeSettings: () => set({ route: "app" }),
  setSettingsSection: (settingsSection) => set({ settingsSection }),
  setCommandPaletteOpen: (commandPaletteOpen) =>
    set(commandPaletteOpen ? { commandPaletteOpen } : { commandPaletteOpen, commandPaletteQuery: "" }),
  toggleCommandPalette: () =>
    set((state) =>
      state.commandPaletteOpen
        ? { commandPaletteOpen: false, commandPaletteQuery: "" }
        : { commandPaletteOpen: true },
    ),
  setCommandPaletteQuery: (commandPaletteQuery) => set({ commandPaletteQuery }),
}));
