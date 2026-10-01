/**
 * The app's keyboard shortcuts, in one table: every menu accelerator of a
 * packaged build and the keys the renderer binds to its own commands. A
 * control's own keys — arrows in a list, Delete on a focused tab — are not in it.
 *
 * The Settings page renders this; the app menu (`src/main/menu.ts`) declares
 * the accelerators that make several of them work when focus is inside a
 * webview. Two declarations of the same key would drift, so this table is the
 * one a person reads and the menu is the one Electron reads — and
 * `tests/unit/main/shortcuts-menu.test.ts` holds them to the same keys: every
 * menu accelerator is a row here, and every Application row with a modifier
 * is a menu accelerator. Two bindings are left out. The development build's
 * `Reload App` (Mod+Alt+R), because a packaged app does not have it; and the
 * toast chord (`components/ui/sonner.tsx`: Cmd+Option+T on a Mac, Ctrl+Shift+T
 * elsewhere), because a row holds one portable binding and this one differs by
 * platform — the Settings page prints it as a footnote instead.
 *
 * A binding is written once, in the portable form (`Mod+K`), and rendered per
 * platform: `Mod` is ⌘ on macOS and Ctrl everywhere else, which is the only
 * difference between the two columns worth encoding.
 */

/** The groups the page prints, in order. */
export const SHORTCUT_GROUPS = ["Application", "Session", "Explorer"] as const;
export type ShortcutGroup = (typeof SHORTCUT_GROUPS)[number];

export type Shortcut = {
  id: string;
  group: ShortcutGroup;
  label: string;
  /** `Mod`, `Alt`, `Shift`, `Ctrl` and a key, joined by `+`. */
  binding: string;
  /** The far end of a range, for the nine tab shortcuts that are one row. */
  through?: string;
};

export const SHORTCUTS: readonly Shortcut[] = [
  { id: "new-session", group: "Application", label: "New session", binding: "Mod+N" },
  { id: "command-palette", group: "Application", label: "Command palette", binding: "Mod+K" },
  { id: "settings", group: "Application", label: "Settings", binding: "Mod+," },
  { id: "close-settings", group: "Application", label: "Close Settings or the palette", binding: "Escape" },
  { id: "toggle-sidebar", group: "Application", label: "Toggle sidebar", binding: "Mod+B" },
  { id: "toggle-explorer", group: "Application", label: "Toggle explorer", binding: "Mod+Alt+B" },
  // The top level only: the threads and new-session screens the session pane
  // has shown. The explorer's tabs have their own strip and are not in it.
  { id: "navigate-back", group: "Application", label: "Back", binding: "Mod+[" },
  { id: "navigate-forward", group: "Application", label: "Forward", binding: "Mod+]" },
  // Renderer-only, like Escape: focus between the sidebar, the session and the
  // explorer, skipping a pane that is shut (`Shell`).
  { id: "next-pane", group: "Application", label: "Focus the next pane", binding: "F6" },
  { id: "previous-pane", group: "Application", label: "Focus the previous pane", binding: "Shift+F6" },

  { id: "send", group: "Session", label: "Send", binding: "Enter" },
  {
    id: "newline",
    group: "Session",
    label: "New line in the composer",
    binding: "Shift+Enter",
  },
  { id: "stop", group: "Session", label: "Stop the current turn", binding: "Escape" },

  { id: "new-file-tab", group: "Explorer", label: "New file tab", binding: "Mod+T" },
  { id: "new-review-tab", group: "Explorer", label: "New review tab", binding: "Mod+Shift+R" },
  { id: "new-browser-tab", group: "Explorer", label: "New browser tab", binding: "Mod+Shift+B" },
  // Control on every platform, not `Mod`: ⌃` is what a person already presses
  // for a terminal, and it is the same key on the machine they came from.
  { id: "new-terminal-tab", group: "Explorer", label: "New terminal tab", binding: "Ctrl+`" },
  { id: "new-drawing-tab", group: "Explorer", label: "New drawing tab", binding: "Mod+Shift+D" },
  { id: "close-tab", group: "Explorer", label: "Close tab", binding: "Mod+W" },
  // The menu's `Reload Page`: the focused browser tab's page, never the app.
  { id: "reload-page", group: "Explorer", label: "Reload the browser page", binding: "Mod+R" },
  // Code and Markdown files, from their own editors.
  { id: "save-file", group: "Explorer", label: "Save the file", binding: "Mod+S" },
  // The file tree's focused row; Ctrl+Delete works off macOS too.
  { id: "rename-entry", group: "Explorer", label: "Rename in the file tree", binding: "F2" },
  { id: "trash-entry", group: "Explorer", label: "Move to Trash in the file tree", binding: "Mod+Backspace" },
  // Monaco's tab-focus mode, and the terminal's: while it is on, Tab leaves the
  // editor or the shell rather than typing into it. Control on every platform.
  {
    id: "tab-focus-mode",
    group: "Explorer",
    label: "Toggle Tab moving focus out of an editor or terminal",
    binding: "Ctrl+Shift+M",
  },
  {
    id: "switch-tab",
    group: "Explorer",
    label: "Switch to tab 1–9",
    binding: "Mod+1",
    through: "Mod+9",
  },
];

/** How a modifier prints on each platform. */
const GLYPHS: Record<string, { mac: string; other: string }> = {
  Mod: { mac: "⌘", other: "Ctrl" },
  Ctrl: { mac: "⌃", other: "Ctrl" },
  Alt: { mac: "⌥", other: "Alt" },
  Shift: { mac: "⇧", other: "Shift" },
  Enter: { mac: "⏎", other: "Enter" },
  // "esc" rather than ⎋: the glyph exists, but it is drawn at cap height in
  // most mono faces and reads as a smudge next to ⌘K. Apple's own keycaps say
  // esc.
  Escape: { mac: "esc", other: "Esc" },
  Backspace: { mac: "⌫", other: "Backspace" },
};

/**
 * The binding as one string: `⌘K` on macOS, `Ctrl+K` elsewhere.
 *
 * macOS runs the glyphs together, which is how every macOS menu prints them;
 * every other platform joins with `+`, which is how every other platform does.
 */
export function shortcutKeys(binding: string, mac: boolean): string {
  const parts = binding.split("+").map((part) => {
    const glyph = GLYPHS[part];
    if (glyph) {
      return mac ? glyph.mac : glyph.other;
    }
    return part.length === 1 ? part.toUpperCase() : part;
  });
  return mac ? parts.join("") : parts.join("+");
}

/** The shortcuts of one group, in declaration order. */
export function shortcutsIn(group: ShortcutGroup): Shortcut[] {
  return SHORTCUTS.filter((shortcut) => shortcut.group === group);
}
