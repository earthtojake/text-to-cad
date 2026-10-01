/**
 * Monaco, wired to this app rather than to the internet.
 *
 * Two things have to be done before the first editor mounts, and both are
 * silent failures if they are not:
 *
 * 1. **The loader.** `@monaco-editor/react` fetches Monaco from a CDN by
 *    default. In a packaged desktop app that is a blank pane on an aeroplane;
 *    `loader.config({ monaco })` points it at the copy in `node_modules`,
 *    which the bundler then puts in the build.
 * 2. **The workers.** Monaco's tokenizer and its language services run in web
 *    workers. Without `MonacoEnvironment.getWorker` it falls back to running
 *    them on the main thread, which mostly works and then freezes the window
 *    on a large file. Vite's `?worker` imports are how a worker gets bundled
 *    (and why `electron.vite.config.ts` sets `worker.format: "es"`).
 *
 * The two themes are the app's tokens, hand-converted: Monaco takes hex, not
 * `var(--background)`, so this is the one place in the renderer where a colour
 * is written out. The values are the surface tokens
 * `@text-to-cad/ui/tokens.css` states in oklch — dark `--background` is
 * `oklch(0.28 0 0)`, `#292929`, and so on down `SURFACE`. The editor sits on
 * the shell's own background: an editor a shade off the pane around it reads
 * as a slab with seams at every edge, which is what the stacked diffs in the
 * review showed when it was `#0a0a0a`.
 *
 * The pure half — the language table, the shared editor options — is
 * `./monaco`, so nothing has to import all of this to ask what language a file
 * is written in.
 */
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
// `monaco-editor/editor/…`, not `monaco-editor/esm/vs/editor/…`. Since 0.5x
// the package has an exports map whose `"./*"` entry already points at
// `./esm/vs/*.js`, so the older deep path resolves to `esm/vs/esm/vs/…` and
// Rollup fails to find it — with a message that names the file, not the map.
import editorWorker from "monaco-editor/editor/editor.worker?worker";
import cssWorker from "monaco-editor/language/css/css.worker?worker";
import htmlWorker from "monaco-editor/language/html/html.worker?worker";
import jsonWorker from "monaco-editor/language/json/json.worker?worker";
import tsWorker from "monaco-editor/language/typescript/ts.worker?worker";

import { isMac } from "@renderer/lib/platform";

import { MONACO_DARK, MONACO_LIGHT, MONACO_TRANSCRIPT_DARK, MONACO_TRANSCRIPT_LIGHT } from "./monaco";

/* -------------------------------------------------------------------------- */
/* Themes                                                                      */
/* -------------------------------------------------------------------------- */

/** shadcn neutral, as hex. Named so a reader can check them against the CSS. */
const NEUTRAL = {
  white: "#ffffff",
  n50: "#fafafa",
  n100: "#f5f5f5",
  n200: "#e5e5e5",
  n400: "#a1a1a1",
  n500: "#737373",
  n700: "#404040",
  n800: "#262626",
  n900: "#171717",
  n950: "#0a0a0a",
} as const;

/**
 * The shell's surface tokens in dark mode (`.dark` in tokens.css), as hex.
 * Light mode's surfaces are the neutral scale above: `--background` and
 * `--card` are white, `--muted` is n100.
 */
const SURFACE = {
  background: "#292929", // --background  oklch(0.28 0 0)
  card: "#303030", // --card / --popover  oklch(0.31 0 0)
  muted: "#383838", // --muted / --secondary  oklch(0.34 0 0)
  accent: "#424242", // --accent  oklch(0.38 0 0)
  border: "#ffffff1a", // --border  oklch(1 0 0 / 10%)
  mutedForeground: "#b4b4b4", // --muted-foreground  oklch(0.77 0 0)
} as const;

/**
 * Diff colours, in two strengths.
 *
 * Monaco paints the *line* background and then the *changed-text* background
 * on top of it, so one value for both compounds: a wholly-added block comes
 * out as a solid slab you cannot read code through. The line tint is what says
 * "this side changed" and stays faint; the text tint is what says "these
 * characters changed" and only ever covers a few words.
 */
const DIFF = {
  insertedLineLight: "#16a34a14",
  removedLineLight: "#dc262614",
  insertedTextLight: "#16a34a38",
  removedTextLight: "#dc262638",
  insertedLineDark: "#22c55e14",
  removedLineDark: "#ef444414",
  insertedTextDark: "#22c55e3d",
  removedTextDark: "#ef44443d",
} as const;

const lightTheme: monaco.editor.IStandaloneThemeData = {
  base: "vs",
  inherit: true,
  rules: [],
  colors: {
    "editor.background": NEUTRAL.white,
    "editor.foreground": NEUTRAL.n950,
    "editorLineNumber.foreground": NEUTRAL.n400,
    "editorLineNumber.activeForeground": NEUTRAL.n700,
    "editor.lineHighlightBackground": NEUTRAL.n100,
    "editor.lineHighlightBorder": "#00000000",
    "editor.selectionBackground": NEUTRAL.n200,
    "editor.inactiveSelectionBackground": NEUTRAL.n100,
    "editorIndentGuide.background1": NEUTRAL.n200,
    "editorWidget.background": NEUTRAL.n50,
    "editorWidget.border": NEUTRAL.n200,
    "editorGutter.background": NEUTRAL.white,
    "scrollbarSlider.background": "#0a0a0a1a",
    "scrollbarSlider.hoverBackground": "#0a0a0a2a",
    "scrollbarSlider.activeBackground": "#0a0a0a3a",
    "diffEditor.insertedTextBackground": DIFF.insertedTextLight,
    "diffEditor.removedTextBackground": DIFF.removedTextLight,
    "diffEditor.insertedLineBackground": DIFF.insertedLineLight,
    "diffEditor.removedLineBackground": DIFF.removedLineLight,
    "diffEditor.unchangedRegionBackground": NEUTRAL.n100,
    "diffEditor.unchangedRegionForeground": NEUTRAL.n500,
    "diffEditor.unchangedCodeBackground": "#00000000",
  },
};

const darkTheme: monaco.editor.IStandaloneThemeData = {
  base: "vs-dark",
  inherit: true,
  rules: [],
  colors: {
    "editor.background": SURFACE.background,
    "editor.foreground": NEUTRAL.n50,
    "editorLineNumber.foreground": NEUTRAL.n500,
    "editorLineNumber.activeForeground": NEUTRAL.n200,
    "editor.lineHighlightBackground": SURFACE.card,
    "editor.lineHighlightBorder": "#00000000",
    "editor.selectionBackground": "#525252",
    "editor.inactiveSelectionBackground": SURFACE.accent,
    "editorIndentGuide.background1": SURFACE.muted,
    "editorWidget.background": SURFACE.card,
    "editorWidget.border": SURFACE.border,
    "editorGutter.background": SURFACE.background,
    "scrollbarSlider.background": "#fafafa1a",
    "scrollbarSlider.hoverBackground": "#fafafa2a",
    "scrollbarSlider.activeBackground": "#fafafa3a",
    "diffEditor.insertedTextBackground": DIFF.insertedTextDark,
    "diffEditor.removedTextBackground": DIFF.removedTextDark,
    "diffEditor.insertedLineBackground": DIFF.insertedLineDark,
    "diffEditor.removedLineBackground": DIFF.removedLineDark,
    "diffEditor.unchangedRegionBackground": SURFACE.card,
    "diffEditor.unchangedRegionForeground": SURFACE.mutedForeground,
    "diffEditor.unchangedCodeBackground": "#00000000",
  },
};

/* -------------------------------------------------------------------------- */
/* Setup                                                                       */
/* -------------------------------------------------------------------------- */

declare global {
  interface Window {
    MonacoEnvironment?: monaco.Environment;
  }
}

let configured = false;

/**
 * Idempotent, and safe to call from a component's render: everything it does
 * is a module-level registration.
 */
export function setupMonaco(): void {
  if (configured) {
    return;
  }
  configured = true;

  window.MonacoEnvironment = {
    getWorker(_id, label) {
      switch (label) {
        case "json":
          return new jsonWorker();
        case "css":
        case "scss":
        case "less":
          return new cssWorker();
        case "html":
        case "handlebars":
        case "razor":
          return new htmlWorker();
        case "typescript":
        case "javascript":
          return new tsWorker();
        default:
          return new editorWorker();
      }
    },
  };

  loader.config({ monaco });
  // Tab-focus mode (Tab leaves the editor rather than indenting) is Monaco's
  // Ctrl+Shift+M on macOS and Ctrl+M elsewhere. The shortcut table and the
  // terminal say Ctrl+Shift+M on every platform, so it is that here too; the
  // native Ctrl+M still works.
  if (!isMac) {
    monaco.editor.addKeybindingRule({
      keybinding: monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyM,
      command: "editor.action.toggleTabFocusMode",
    });
  }
  // Every theme the renderer uses, registered here, once, in this order.
  // Monaco themes cannot inherit from each other (`base` is only `vs` or
  // `vs-dark`), so the transcript's are the shell's colours spread, with a
  // transparent background.
  monaco.editor.defineTheme(MONACO_LIGHT, lightTheme);
  monaco.editor.defineTheme(MONACO_DARK, darkTheme);
  monaco.editor.defineTheme(MONACO_TRANSCRIPT_LIGHT, transparent(lightTheme));
  monaco.editor.defineTheme(MONACO_TRANSCRIPT_DARK, transparent(darkTheme));
}

function transparent(theme: monaco.editor.IStandaloneThemeData): monaco.editor.IStandaloneThemeData {
  return {
    ...theme,
    colors: { ...theme.colors, "editor.background": "#00000000", "editorGutter.background": "#00000000" },
  };
}
