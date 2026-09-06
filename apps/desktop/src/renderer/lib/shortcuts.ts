/**
 * Every keyboard shortcut the app claims, in one table.
 *
 * The Settings page renders this; the app menu (`src/main/menu.ts`) declares
 * the accelerators that make several of them work when focus is inside a
 * webview. Two declarations of the same key would drift, so this table is the
 * one a person reads and the menu is the one Electron reads — and the test in
 * `tests/unit/renderer/shortcuts.test.ts` holds them to the same glyphs.
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
  { id: "new-session", group: "Application", label: "New chat", binding: "Mod+N" },
  { id: "command-palette", group: "Application", label: "Command palette", binding: "Mod+K" },
  { id: "settings", group: "Application", label: "Settings", binding: "Mod+," },
  { id: "close-settings", group: "Application", label: "Close Settings or the palette", binding: "Escape" },
  { id: "toggle-sidebar", group: "Application", label: "Toggle sidebar", binding: "Mod+B" },
  { id: "toggle-explorer", group: "Application", label: "Toggle explorer", binding: "Mod+Alt+B" },

  { id: "send", group: "Session", label: "Send", binding: "Enter" },
  {
    id: "newline",
    group: "Session",
    label: "New line in the composer",
    binding: "Shift+Enter",
  },
  { id: "stop", group: "Session", label: "Stop the current turn", binding: "Escape" },

  { id: "close-tab", group: "Explorer", label: "Close tab", binding: "Mod+W" },
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
