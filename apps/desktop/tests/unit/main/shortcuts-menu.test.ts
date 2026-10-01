/**
 * The shortcut table (`src/renderer/lib/shortcuts.ts`) is what a person reads;
 * the app menu (`src/main/menu.ts`) is what Electron reads. Every accelerator
 * of a packaged build's menu is a row in the table, and every Application row
 * with a modifier is an accelerator in the menu.
 */
import type { MenuItemConstructorOptions } from "electron";
import { expect, it, vi } from "vitest";

vi.mock("electron", () => ({
  Menu: { buildFromTemplate: (template: unknown) => template, setApplicationMenu: vi.fn() },
  app: { name: "text-to-cad", isPackaged: true, on: vi.fn() },
  dialog: {},
  shell: {},
}));
vi.mock("@main/ipc/register", () => ({ emit: vi.fn() }));
vi.mock("@main/browser/service", () => ({ browserService: {} }));
import { buildMenu } from "@main/menu";

// The table is renderer code, and `tsconfig.node.json` may not list renderer
// files; a computed specifier keeps the compiler out while Vite resolves the
// alias. The module is pure data, so a Node test can load it.
type Shortcut = { id: string; group: string; binding: string };
const tableModule = "@renderer/lib/shortcuts";
const { SHORTCUTS } = (await import(/* @vite-ignore */ tableModule)) as { SHORTCUTS: readonly Shortcut[] };

const flatten = (items: MenuItemConstructorOptions[]): MenuItemConstructorOptions[] =>
  items.flatMap((item) => [item, ...(Array.isArray(item.submenu) ? flatten(item.submenu) : [])]);

/** Electron's `CmdOrCtrl`, and the platform-specific `Cmd`/`Ctrl` a branch picks, as the table's `Mod`. */
const portable = (accelerator: string) => accelerator.replace(/^(CmdOrCtrl|Cmd|Ctrl)\+/, "Mod+");

const accelerators = flatten(
  buildMenu(() => null, () => { throw new Error("unused"); }, true) as unknown as MenuItemConstructorOptions[],
)
  .map((item) => item.accelerator)
  .filter((accelerator): accelerator is string => typeof accelerator === "string")
  .map(portable);

/**
 * Renderer-only by nature: Escape is not a menu key, and F6 moves focus between the renderer's
 * own panes — a menu accelerator would take it from a webview that has focus and do nothing there.
 * `focus-notifications` is the Toaster's own hotkey listener.
 */
const RENDERER_ONLY = new Set(["close-settings", "next-pane", "previous-pane", "focus-notifications"]);

it("lists every packaged menu accelerator in the shortcut table", () => {
  const bindings = new Set(SHORTCUTS.map((shortcut) => shortcut.binding));
  expect(accelerators.length).toBeGreaterThan(0);
  expect(accelerators.filter((accelerator) => !bindings.has(accelerator)), "menu accelerators missing from SHORTCUTS").toEqual([]);
});

it("gives every Application shortcut a menu accelerator", () => {
  const menu = new Set(accelerators);
  const missing = SHORTCUTS.filter(
    (shortcut) => shortcut.group === "Application" && !RENDERER_ONLY.has(shortcut.id) && !menu.has(shortcut.binding),
  ).map((shortcut) => `${shortcut.id} ${shortcut.binding}`);
  expect(missing, "Application shortcuts with no menu accelerator").toEqual([]);
});

/** The menu as Electron builds it on a platform; `buildMenu` reads `process.platform` when it runs. */
function acceleratorsOn(platform: NodeJS.Platform): string[] {
  const original = Object.getOwnPropertyDescriptor(process, "platform")!;
  Object.defineProperty(process, "platform", { value: platform });
  try {
    return flatten(buildMenu(() => null, () => { throw new Error("unused"); }, true) as unknown as MenuItemConstructorOptions[])
      .map((item) => item.accelerator)
      .filter((accelerator): accelerator is string => typeof accelerator === "string");
  } finally {
    Object.defineProperty(process, "platform", original);
  }
}

it.each(["win32", "linux"] as const)("binds no chord that combines Ctrl and Alt on %s, where it arrives as AltGr", (platform) => {
  const chords = acceleratorsOn(platform);
  expect(chords.length).toBeGreaterThan(0);
  expect(chords.filter((chord) => /(CmdOrCtrl|Ctrl|Control)\+/.test(chord) && /\bAlt\+/.test(chord))).toEqual([]);
});

it("keeps the Mac's Cmd+Option+B and lists the other platforms' chord in the table", () => {
  expect(acceleratorsOn("darwin")).toContain("CmdOrCtrl+Alt+B");
  const row = SHORTCUTS.find((shortcut) => shortcut.id === "toggle-explorer") as Shortcut & { otherBinding?: string };
  expect(acceleratorsOn("linux").map(portable)).toContain(row.otherBinding);
});
