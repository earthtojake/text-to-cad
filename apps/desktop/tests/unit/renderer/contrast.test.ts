import { describe, expect, it } from "vitest";

import agentSetup from "../../../src/renderer/features/session/agent-setup.tsx?raw";
import subagentRow from "../../../src/renderer/features/session/parts/SubagentRow.tsx?raw";
import sessionRow from "../../../src/renderer/features/sidebar/SessionRow.tsx?raw";
import authPrompt from "../../../src/renderer/features/session/AuthPrompt.tsx?raw";

/**
 * Text contrast, computed from the colours the stylesheets declare: WCAG 1.4.3 asks 4.5:1 for
 * body text. `--muted-foreground` is the app's secondary text, drawn on the page and on every
 * quiet surface — a row's hover, a muted badge, the sidebar — in both themes.
 */

// Read from disk: Vitest serves a stylesheet's `?raw` as an empty string (it does not process
// CSS). `tsconfig.web.json` has no Node types, so `node:fs` comes in through a computed specifier
// (as tests/unit/main/shortcuts-menu.test.ts takes the renderer's table) and the directory
// through Vitest's `import.meta.dirname`.
const fsModule = "node:fs";
const { readFileSync } = (await import(/* @vite-ignore */ fsModule)) as { readFileSync: (file: string, encoding: "utf8") => string };
const here = (import.meta as ImportMeta & { dirname: string }).dirname;
const tokens = readFileSync(`${here}/../../../../../packages/ui/src/styles/tokens.css`, "utf8");

/** `oklch(L C h)` (L as a number or a percentage), as linear sRGB. */
function oklchToLinear(value: string): [number, number, number] {
  const match = /oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)/.exec(value);
  if (!match) throw new Error(`not an opaque oklch(): ${value}`);
  const L = Number(match[1]) / (match[2] ? 100 : 1);
  const C = Number(match[3]);
  const h = (Number(match[4]) * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const clamp = (x: number) => Math.min(1, Math.max(0, x));
  return [
    clamp(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    clamp(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    clamp(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ];
}

const luminance = (value: string) => {
  const [r, g, b] = oklchToLinear(value);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

export function contrast(foreground: string, background: string): number {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

/** The custom properties one rule block of `css` declares. */
function block(css: string, selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no ${selector} block`);
  const body = css.slice(start, css.indexOf("\n}", start)).replace(/\/\*[\s\S]*?\*\//g, "");
  return Object.fromEntries([...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((match) => [match[1]!, match[2]!.trim()]));
}

/** Tailwind 4's greens (`tailwindcss/theme.css`), which this app does not redefine. */
const EMERALD: Record<string, string> = {
  "emerald-400": "oklch(76.5% 0.177 163.223)",
  "emerald-500": "oklch(69.6% 0.17 162.48)",
  "emerald-600": "oklch(59.6% 0.145 163.225)",
  "emerald-700": "oklch(50.8% 0.118 165.612)",
};

const THEMES = { light: block(tokens, ":root"), dark: block(tokens, ".dark") };
/** The opaque surfaces muted text is drawn on. */
const SURFACES = ["--background", "--card", "--popover", "--muted", "--secondary", "--accent", "--sidebar", "--sidebar-accent"];

describe("text contrast", () => {
  for (const [theme, values] of Object.entries(THEMES)) {
    it(`gives --muted-foreground 4.5:1 on every quiet surface (${theme})`, () => {
      const failing = SURFACES.map((surface) => [surface, contrast(values["--muted-foreground"]!, values[surface]!)] as const)
        .filter(([, ratio]) => ratio < 4.5)
        .map(([surface, ratio]) => `${surface} ${ratio.toFixed(2)}:1`);
      expect(failing).toEqual([]);
    });
  }

  it("draws the secondary text of a subagent, a session's project and a sign-in hint at full muted strength", () => {
    // `text-muted-foreground/70` on the sidebar was 2.7:1: a fraction of a colour that is only just
    // 4.5:1 at full strength.
    for (const source of [subagentRow, sessionRow, authPrompt]) {
      expect(source).not.toMatch(/<(span|p)[^>]*text-muted-foreground\/\d+/);
    }
  });

  it("says Ready in a green that is 4.5:1 on the page", () => {
    const light = /ready \? "text-(emerald-\d+)/.exec(agentSetup)?.[1];
    expect(light).toBeDefined();
    const green = EMERALD[light!]!;
    expect(contrast(green, THEMES.light["--background"]!)).toBeGreaterThanOrEqual(4.5);
    const dark = /ready \? "text-emerald-\d+ dark:text-(emerald-\d+)/.exec(agentSetup)?.[1];
    const darkGreen = EMERALD[dark!]!;
    expect(contrast(darkGreen, THEMES.dark["--background"]!)).toBeGreaterThanOrEqual(4.5);
  });
});
