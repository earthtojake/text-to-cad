/**
 * generate/syntax.ts
 *
 * Generates a Shiki/VSCode-format syntax theme from the resolved palette scales.
 *
 * Strategy:
 *   - Each SyntaxRole has a default palette assignment per polarity (from syntax-template.ts).
 *   - The assignment is resolved to a concrete color from the appropriate scale.step.
 *   - Minimum APCA contrast against the code background is enforced.
 *   - Roles are emitted as tokenColors scopes in VSCode theme format.
 *
 * Calibration target: the default light/dark assignments reproduce the visual
 * character of github-light / github-dark, adapted to our palette's hue choices.
 *
 * Explicit VSCode themes (imported JSON) pass through unmodified.
 */

import Color from 'colorjs.io';
import { nsName } from '../contract/namespace';
import type { Polarity, Scales, SyntaxRole } from '../contract/roles';
import { SYNTAX_TEMPLATE } from '../contract/syntax-template';
import { SYNTAX_MIN_APCA } from '../contract/targets';
import { colorToHex, resolveScaleRef } from './color-format';

// ── Types ─────────────────────────────────────────────────────────────────────

export type SyntaxThemeInput =
  | { generate: true; roleOverrides?: Partial<Record<SyntaxRole, string>> }
  | { vscodeTheme: object }
  | string; // bundled Shiki theme name passthrough

export type GeneratedSyntaxTheme = object; // VSCode theme JSON format

// ── Palette ref resolution ────────────────────────────────────────────────────

/**
 * Resolve a palette ref and, if APCA vs bg is below the minimum, climb up
 * one step (toward higher contrast) until the threshold is met or we run out.
 */
function resolveWithMinContrast(
  ref: string,
  scales: Scales,
  bgColor: Color,
  minLc: number,
  _polarity: Polarity
): string {
  const [scaleName, stepOrContrast] = ref.split('.') as [keyof Scales, string];
  const scale = scales[scaleName];
  if (!scale) return resolveScaleRef(ref, scales);

  if (stepOrContrast === 'contrast') {
    return scale.contrast;
  }

  let stepNum = parseInt(stepOrContrast, 10);
  if (isNaN(stepNum)) return resolveScaleRef(ref, scales);

  const contrastDirection = 1; // always move toward step 12 for more contrast

  for (let attempt = 0; attempt < 4; attempt++) {
    const color = scale.steps[Math.min(11, stepNum - 1)];
    try {
      const c = new Color(color);
      const lc = Math.abs(c.contrastAPCA(bgColor) as number);
      if (lc >= minLc) return color;
    } catch {
      return color;
    }
    stepNum = Math.min(12, stepNum + contrastDirection);
  }

  return scale.steps[Math.min(11, stepNum - 1)];
}

// ── CSS-variable map ──────────────────────────────────────────────────────────

/**
 * Produce per-theme CSS custom properties for syntax highlighting.
 *
 * Each `--syntax-<role>` var holds the contrast-checked hex color for that
 * token role; the single static Shiki theme (emit-shiki.ts) references these
 * vars so switching themes requires only a class swap, not re-tokenizing.
 *
 * Alpha-composited editor chrome colors (selection, findMatch, scrollbar) that
 * cannot be expressed as a bare `var()` in a Shiki `colors` object are emitted
 * as `--syntax-editor-*` for reference by the host app; non-alpha colors reuse
 * existing palette vars (`--background`, `--foreground`, `--neutral-*`).
 */
export function generateSyntaxVars(
  scales: Scales,
  polarity: Polarity,
  input: SyntaxThemeInput
): Record<string, string> {
  if (typeof input === 'string' || 'vscodeTheme' in input) {
    return {};
  }

  const { roleOverrides = {} } = input;
  const bgColorStr = scales.neutral.steps[0];
  const bgColor = new Color(bgColorStr);
  const vars: Record<string, string> = {};

  for (const [role, entry] of Object.entries(SYNTAX_TEMPLATE) as Array<
    [SyntaxRole, (typeof SYNTAX_TEMPLATE)[SyntaxRole]]
  >) {
    const defaultRef = polarity === 'light' ? entry.lightDefault : entry.darkDefault;
    const ref = roleOverrides[role] ?? defaultRef;
    const minLc = SYNTAX_MIN_APCA[role] ?? SYNTAX_MIN_APCA['default'] ?? 45;
    const resolvedColor = resolveWithMinContrast(ref, scales, bgColor, minLc, polarity);
    vars[nsName(`syntax-${role}`)] = colorToHex(resolvedColor);
  }

  // Alpha-composited editor chrome vars (cannot be a plain var() in Shiki colors).
  // Non-alpha chrome colors (bg, fg, line-highlight, cursor, line-number, bracket)
  // reuse existing --em-background / --em-foreground / --em-neutral-* palette vars.
  const selectionHex = colorToHex(scales.blue.steps[5]);
  vars[nsName('syntax-editor-selection-bg')] = selectionHex + '40';
  vars[nsName('syntax-editor-find-match-bg')] = selectionHex + '60';
  vars[nsName('syntax-editor-find-match-hl')] = selectionHex + '30';
  vars[nsName('syntax-editor-scrollbar-bg')] = colorToHex(scales.neutral.steps[5]) + '60';
  vars[nsName('syntax-editor-scrollbar-hover')] = colorToHex(scales.neutral.steps[6]) + '80';

  return vars;
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Generate a Shiki/VSCode-format syntax theme from the resolved palette.
 *
 * Returns the theme object ready to pass to shiki's createHighlighterCoreSync.
 */
export function generateSyntaxTheme(
  scales: Scales,
  polarity: Polarity,
  input: SyntaxThemeInput
): GeneratedSyntaxTheme {
  // Pass through explicit themes unchanged
  if (typeof input === 'string') {
    return { name: input } as GeneratedSyntaxTheme;
  }
  if ('vscodeTheme' in input) {
    return input.vscodeTheme as GeneratedSyntaxTheme;
  }

  const { roleOverrides = {} } = input;

  // Code background = neutral scale step 1 (which is also --background in our template)
  const bgColorStr = scales.neutral.steps[0];
  const bgColor = new Color(bgColorStr);

  // Foreground = neutral step 12
  const fgColorStr = scales.neutral.steps[11];

  const tokenColors: Array<{
    scope: string | string[];
    settings: { foreground?: string; fontStyle?: string };
  }> = [];

  for (const [role, entry] of Object.entries(SYNTAX_TEMPLATE) as Array<
    [SyntaxRole, (typeof SYNTAX_TEMPLATE)[SyntaxRole]]
  >) {
    // Resolve the palette ref
    const defaultRef = polarity === 'light' ? entry.lightDefault : entry.darkDefault;
    const ref = roleOverrides[role] ?? defaultRef;

    const minLc = SYNTAX_MIN_APCA[role] ?? SYNTAX_MIN_APCA['default'] ?? 45;
    const resolvedColor = resolveWithMinContrast(ref, scales, bgColor, minLc, polarity);
    const hexColor = colorToHex(resolvedColor);

    const settings: { foreground?: string; fontStyle?: string } = { foreground: hexColor };

    // Comments get italic by convention (matching gh-dark style)
    if (role === 'comment') {
      settings.fontStyle = 'italic';
    }

    tokenColors.push({
      scope: entry.scopes,
      settings,
    });
  }

  const themeName = `em-${polarity}`;
  const bgHex = colorToHex(bgColorStr);
  const fgHex = colorToHex(fgColorStr);
  const selectionHex = colorToHex(scales.blue.steps[5]); // blue.6
  const cursorHex = fgHex;

  return {
    name: themeName,
    type: polarity,
    colors: {
      'editor.background': bgHex,
      'editor.foreground': fgHex,
      'editor.selectionBackground': colorToHex(scales.blue.steps[5]) + '40', // with alpha
      'editor.lineHighlightBackground': colorToHex(scales.neutral.steps[1]),
      'editorCursor.foreground': cursorHex,
      'editor.findMatchBackground': selectionHex + '60',
      'editor.findMatchHighlightBackground': selectionHex + '30',
      'editorLineNumber.foreground': colorToHex(scales.neutral.steps[8]),
      'editorLineNumber.activeForeground': colorToHex(scales.neutral.steps[11]),
      'editorIndentGuide.background': colorToHex(scales.neutral.steps[4]),
      'editorBracketMatch.background': colorToHex(scales.blue.steps[3]),
      'editorBracketMatch.border': colorToHex(scales.blue.steps[6]),
      'scrollbarSlider.background': colorToHex(scales.neutral.steps[5]) + '60',
      'scrollbarSlider.hoverBackground': colorToHex(scales.neutral.steps[6]) + '80',
    },
    tokenColors,
    semanticHighlighting: true,
  };
}
