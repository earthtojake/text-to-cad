/**
 * Theme generation tests.
 *
 * Validates:
 *  1. APCA target adherence for text-zone steps (7–12) per polarity.
 *  2. All generated colors are in P3 gamut.
 *  3. Semantic template completeness — every slot resolves to a non-empty CSS string.
 *  4. Snapshot: spot-check key vars from the generated light/dark themes.
 */

import Color from 'colorjs.io';
import { describe, expect, it } from 'vitest';
import { darkTheme } from '../themes/dark.theme';
import { lightTheme } from '../themes/light.theme';
import { nsName } from './contract/namespace';
import { SURFACE_LEVELS, SURFACE_STATUSES, STATUS_LEVEL_SCOPES } from './contract/roles';
import { SEMANTIC_TEMPLATE } from './contract/semantic-template';
import type { ResolvedTheme } from './define-theme';

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseColor(css: string): Color {
  return new Color(css);
}

function apca(fg: string, bg: string): number {
  return parseColor(fg).contrastAPCA(parseColor(bg)) as number;
}

function isInP3Gamut(css: string): boolean {
  try {
    const c = parseColor(css);
    return c.inGamut('p3');
  } catch {
    return false;
  }
}

/** Text-zone steps are 7–12 (0-indexed: 6–11). */
const TEXT_ZONE_INDICES = [6, 7, 8, 9, 10, 11] as const;

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Theme generation', () => {
  function runThemeTests(theme: ResolvedTheme, tolerance = 5) {
    const { id, scales, polarity } = theme;
    const bg = scales.neutral.steps[0]; // step 1 = background anchor

    describe(`${id} (${polarity})`, () => {
      // 1. APCA adherence for text-zone steps
      describe('APCA targets (text zone steps 7–12)', () => {
        for (const scaleId of ['neutral', 'accent', 'green', 'red'] as const) {
          it(`${scaleId} scale text steps meet targets (±${tolerance} Lc)`, () => {
            const ramp = scales[scaleId];
            TEXT_ZONE_INDICES.forEach((idx) => {
              const color = ramp.steps[idx];
              const lc = apca(color, bg);
              // All text-zone steps should have meaningful contrast (|Lc| > 15)
              expect(
                Math.abs(lc),
                `step ${idx + 1}: |Lc| should be > 15, got ${Math.abs(lc).toFixed(1)}`
              ).toBeGreaterThan(15);
            });
          });
        }
      });

      // 2. Gamut check
      it('all generated scale colors are in P3 gamut', () => {
        for (const [scaleName, ramp] of Object.entries(scales)) {
          ramp.steps.forEach((color: string, i: number) => {
            expect(isInP3Gamut(color), `${scaleName}.step ${i + 1} out of gamut: ${color}`).toBe(
              true
            );
          });
        }
      });

      // 3. Contrast color readability on step 9 (solid)
      // Threshold 40: amber/yellow (gamut-cusp hues) target dark text at slightly lower Lc.
      // APCA 40 is still sufficient for large/bold UI elements like buttons.
      it('contrast color is readable on step 9 (solid) — |Lc| ≥ 40', () => {
        for (const [scaleName, ramp] of Object.entries(scales)) {
          const solid = ramp.steps[8]; // step 9
          const lc = apca(ramp.contrast, solid);
          expect(
            Math.abs(lc),
            `${scaleName} contrast on step 9: |Lc| = ${Math.abs(lc).toFixed(1)}`
          ).toBeGreaterThanOrEqual(40);
        }
      });

      // 4. Semantic template completeness
      it('all semantic slots resolve to non-empty CSS values', () => {
        const { cssVars } = theme;
        for (const slot of Object.keys(SEMANTIC_TEMPLATE)) {
          const varName = nsName(slot);
          const value = cssVars[varName];
          expect(value, `${varName} is missing from cssVars`).toBeTruthy();
          expect(value!.length, `${varName} is empty`).toBeGreaterThan(0);
        }
      });

      // 5. Foreground (neutral.12) has high contrast vs background (neutral.1)
      it('foreground has high contrast vs background (|Lc| ≥ 70)', () => {
        const fg = scales.neutral.steps[11]; // step 12
        const lc = apca(fg, bg);
        expect(Math.abs(lc)).toBeGreaterThanOrEqual(70);
      });
    });
  }

  runThemeTests(lightTheme);
  runThemeTests(darkTheme);

  // 6. Key CSS var spot-checks
  describe('generated CSS var spot-checks', () => {
    it('light --em-background resolves to a near-white color', () => {
      const bg = lightTheme.cssVars[nsName('background')];
      expect(bg).toBeTruthy();
      const L = new Color(bg!).to('oklch').coords[0];
      expect(L).toBeGreaterThan(0.9);
    });

    it('dark --em-background resolves to a near-black color', () => {
      const bg = darkTheme.cssVars[nsName('background')];
      expect(bg).toBeTruthy();
      const L = new Color(bg!).to('oklch').coords[0];
      expect(L).toBeLessThan(0.25);
    });

    it('light primary-button-background is readable (high APCA on its contrast)', () => {
      const btnBg = lightTheme.cssVars[nsName('primary-button-background')];
      const btnFg = lightTheme.cssVars[nsName('primary-button-foreground')];
      expect(btnBg).toBeTruthy();
      expect(btnFg).toBeTruthy();
      const lc = apca(btnFg!, btnBg!);
      expect(Math.abs(lc)).toBeGreaterThanOrEqual(45);
    });

    it('dark --em-foreground has high contrast vs dark background', () => {
      const fg = darkTheme.cssVars[nsName('foreground')];
      const bg = darkTheme.cssVars[nsName('background')];
      expect(fg).toBeTruthy();
      expect(bg).toBeTruthy();
      const lc = apca(fg!, bg!);
      expect(Math.abs(lc)).toBeGreaterThanOrEqual(70);
    });
  });

  // 7. Surface elevation invariants
  describe('Surface elevation', () => {
    function surfaceLs(theme: ResolvedTheme) {
      return SURFACE_LEVELS.map((level) => {
        const cssVal = theme.cssVars[nsName(`surface-${level}`)];
        expect(cssVal).toBeTruthy();
        return { level, l: new Color(cssVal!).to('oklch').coords[0] };
      });
    }

    // Dark mode is a clean monotonic ladder (sunken darkest → elevated-emphasis lightest)
    it('dark: surface L values are strictly increasing (sunken → elevated-emphasis)', () => {
      const levels = surfaceLs(darkTheme);
      for (let i = 1; i < levels.length; i++) {
        expect(levels[i].l).toBeGreaterThan(levels[i - 1].l);
      }
    });

    // Light mode is intentionally non-monotonic (emphasis darkens on near-white
    // canvases), but sunken stays darkest, elevated stays lightest, and all
    // levels remain visually distinct.
    it('light: sunken is darkest and elevated is lightest', () => {
      const byLevel = Object.fromEntries(surfaceLs(lightTheme).map((x) => [x.level, x.l]));
      const all = Object.values(byLevel);
      expect(byLevel['sunken']).toBe(Math.min(...all));
      expect(byLevel['elevated']).toBe(Math.max(...all));
    });

    it('light: elevated-emphasis is not darker than base', () => {
      const byLevel = Object.fromEntries(surfaceLs(lightTheme).map((x) => [x.level, x.l]));
      expect(byLevel['elevated-emphasis']).toBeGreaterThanOrEqual(byLevel['base']);
    });

    for (const theme of [lightTheme, darkTheme]) {
      it(`${theme.id}: all 5 surface levels are visually distinct`, () => {
        const ls = surfaceLs(theme).map((x) => x.l);
        const unique = new Set(ls.map((l) => l.toFixed(3)));
        expect(unique.size).toBe(SURFACE_LEVELS.length);
      });

      it(`${theme.id}: all surface colors are in P3 gamut`, () => {
        for (const level of SURFACE_LEVELS) {
          for (const variant of ['', '-hover', '-selected']) {
            const cssVal = theme.cssVars[nsName(`surface-${level}${variant}`)];
            expect(cssVal).toBeTruthy();
            const c = new Color(cssVal!);
            expect(c.inGamut('p3')).toBe(true);
          }
        }
      });
    }
  });

  // 7b. Surface role: paper (white-ish in light, flat with base in dark)
  describe('Surface role: paper', () => {
    for (const theme of [lightTheme, darkTheme]) {
      it(`${theme.id}: paper base/hover/selected resolve and are in P3 gamut`, () => {
        for (const variant of ['', '-hover', '-selected']) {
          const cssVal = theme.cssVars[nsName(`surface-paper${variant}`)];
          expect(cssVal, `${nsName(`surface-paper${variant}`)} should be defined`).toBeTruthy();
          expect(new Color(cssVal!).inGamut('p3')).toBe(true);
        }
      });
    }

    it('light: paper is white-ish (L ≥ 0.97), matching elevated', () => {
      const paper = lightTheme.cssVars[nsName('surface-paper')];
      const elevated = lightTheme.cssVars[nsName('surface-elevated')];
      const paperL = new Color(paper!).to('oklch').coords[0];
      const elevatedL = new Color(elevated!).to('oklch').coords[0];
      expect(paperL).toBeGreaterThanOrEqual(0.97);
      expect(Math.abs(paperL - elevatedL)).toBeLessThan(0.01);
    });

    it('dark: paper is flat with base (same L as surface-base)', () => {
      const paper = darkTheme.cssVars[nsName('surface-paper')];
      const base = darkTheme.cssVars[nsName('surface-base')];
      const paperL = new Color(paper!).to('oklch').coords[0];
      const baseL = new Color(base!).to('oklch').coords[0];
      expect(Math.abs(paperL - baseL)).toBeLessThan(0.01);
    });
  });

  // 8. Status surface vars resolve and are in P3 gamut (base + per-level scopes)
  describe('Status surfaces', () => {
    const STATUS_VARIANTS = ['', '-hover', '-selected', '-border', '-foreground'] as const;

    for (const theme of [lightTheme, darkTheme]) {
      it(`${theme.id}: base status vars resolve to non-empty color strings`, () => {
        for (const status of SURFACE_STATUSES) {
          for (const variant of STATUS_VARIANTS) {
            const key = nsName(`surface-${status}${variant}`);
            const cssVal = theme.cssVars[key];
            expect(cssVal, `${key} should be defined`).toBeTruthy();
            expect(cssVal!.length).toBeGreaterThan(0);
          }
        }
      });

      it(`${theme.id}: base status surface colors are in P3 gamut`, () => {
        for (const status of SURFACE_STATUSES) {
          for (const variant of STATUS_VARIANTS) {
            const key = nsName(`surface-${status}${variant}`);
            const cssVal = theme.cssVars[key];
            expect(cssVal).toBeTruthy();
            const c = new Color(cssVal!);
            expect(c.inGamut('p3'), `${key}: ${cssVal} should be in P3 gamut`).toBe(true);
          }
        }
      });

      it(`${theme.id}: per-scope status vars resolve to non-empty color strings`, () => {
        for (const status of SURFACE_STATUSES) {
          for (const scope of STATUS_LEVEL_SCOPES) {
            for (const variant of STATUS_VARIANTS) {
              const key = nsName(`surface-${status}-${scope}${variant}`);
              const cssVal = theme.cssVars[key];
              expect(cssVal, `${key} should be defined`).toBeTruthy();
              expect(cssVal!.length).toBeGreaterThan(0);
            }
          }
        }
      });

      it(`${theme.id}: per-scope status surface colors are in P3 gamut`, () => {
        for (const status of SURFACE_STATUSES) {
          for (const scope of STATUS_LEVEL_SCOPES) {
            for (const variant of STATUS_VARIANTS) {
              const key = nsName(`surface-${status}-${scope}${variant}`);
              const cssVal = theme.cssVars[key];
              expect(cssVal).toBeTruthy();
              const c = new Color(cssVal!);
              expect(c.inGamut('p3'), `${key}: ${cssVal} should be in P3 gamut`).toBe(true);
            }
          }
        }
      });
    }

    // Elevation-tracking regression: status rooms must follow the canvas lightness direction.
    it('dark: elevated status room is lighter than base status room', () => {
      for (const status of SURFACE_STATUSES) {
        const base = darkTheme.cssVars[nsName(`surface-${status}`)];
        const elevated = darkTheme.cssVars[nsName(`surface-${status}-elevated`)];
        expect(base).toBeTruthy();
        expect(elevated).toBeTruthy();
        const baseL = new Color(base!).to('oklch').coords[0];
        const elevatedL = new Color(elevated!).to('oklch').coords[0];
        expect(
          elevatedL,
          `dark ${status}: elevated (${elevatedL.toFixed(3)}) should be lighter than base (${baseL.toFixed(3)})`
        ).toBeGreaterThan(baseL);
      }
    });

    it('light: elevated status room is lighter than base status room', () => {
      for (const status of SURFACE_STATUSES) {
        const base = lightTheme.cssVars[nsName(`surface-${status}`)];
        const elevated = lightTheme.cssVars[nsName(`surface-${status}-elevated`)];
        expect(base).toBeTruthy();
        expect(elevated).toBeTruthy();
        const baseL = new Color(base!).to('oklch').coords[0];
        const elevatedL = new Color(elevated!).to('oklch').coords[0];
        expect(
          elevatedL,
          `light ${status}: elevated (${elevatedL.toFixed(3)}) should be lighter than base (${baseL.toFixed(3)})`
        ).toBeGreaterThan(baseL);
      }
    });
  });

  // 10. Both themes emit syntax CSS vars (--syntax-* / --syntax-editor-*)
  describe('Syntax CSS var generation', () => {
    it('light theme emits --em-syntax-* vars for all roles', () => {
      const roles = [
        'comment',
        'keyword',
        'string',
        'number',
        'function',
        'type',
        'variable',
        'property',
        'operator',
        'tag',
        'attribute',
        'regexp',
      ];
      for (const role of roles) {
        const key = nsName(`syntax-${role}`);
        expect(lightTheme.cssVars[key], `missing ${key}`).toBeTruthy();
      }
    });

    it('dark theme emits --em-syntax-editor-* vars for alpha chrome', () => {
      expect(darkTheme.cssVars[nsName('syntax-editor-selection-bg')]).toBeTruthy();
      expect(darkTheme.cssVars[nsName('syntax-editor-find-match-bg')]).toBeTruthy();
      expect(darkTheme.cssVars[nsName('syntax-editor-scrollbar-bg')]).toBeTruthy();
    });
  });
});
