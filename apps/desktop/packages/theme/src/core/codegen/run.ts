#!/usr/bin/env tsx
/**
 * codegen/run.ts — Theme code generation orchestrator.
 *
 * Imports all theme definitions, resolves them into CSS + TS artifacts,
 * and writes the output files.
 *
 * Emits:
 *   theme/__generated__/theme.css           — @layer tokens { :root defaults + per-.em<id> + .density-<id> vars }
 *   theme/__generated__/semantic.css        — @layer tokens { per-theme semantic vars (imported separately) }
 *   theme/__generated__/shiki-themes.gen.ts — single var-based Shiki theme (emSyntaxTheme)
 */

import { writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ALL_DENSITIES } from '../../densities/registry';
import { darkTheme } from '../../themes/dark.theme';
import { lightTheme } from '../../themes/light.theme';
import { solarizedDarkTheme } from '../../themes/solarized-dark.theme';
import { solarizedLightTheme } from '../../themes/solarized-light.theme';
import type { ResolvedDensity } from '../define-density';
import type { ResolvedTheme } from '../define-theme';
import { emitSemanticCss } from './emit-semantic-css';
import { emitShikiThemesTs } from './emit-shiki';
import { emitThemeCss } from './emit-theme-css';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Output directories — generated CSS lands in theme/__generated__/
const GENERATED_DIR = join(__dirname, '..', '..', '__generated__');

const ALL_THEMES: ResolvedTheme[] = [
  lightTheme,
  darkTheme,
  solarizedLightTheme,
  solarizedDarkTheme,
];

const DENSITIES: ResolvedDensity[] = [...ALL_DENSITIES];

function run(): void {
  const themes = ALL_THEMES;
  const densities = DENSITIES;

  console.log(
    `Building ${themes.length} theme(s): ${themes.map((t) => t.id).join(', ')}; ${densities.length} density mode(s): ${densities.map((d) => d.id).join(', ')}`
  );

  // Ensure output directory exists
  mkdirSync(GENERATED_DIR, { recursive: true });

  // theme/__generated__/theme.css
  writeFileSync(join(GENERATED_DIR, 'theme.css'), emitThemeCss(themes, densities), 'utf8');
  console.log('✓ theme/__generated__/theme.css');

  // theme/__generated__/semantic.css
  writeFileSync(join(GENERATED_DIR, 'semantic.css'), emitSemanticCss(themes), 'utf8');
  console.log('✓ theme/__generated__/semantic.css');

  // theme/__generated__/shiki-themes.gen.ts
  writeFileSync(join(GENERATED_DIR, 'shiki-themes.gen.ts'), emitShikiThemesTs(), 'utf8');
  console.log('✓ theme/__generated__/shiki-themes.gen.ts');

  console.log('\nTheme build complete.');
}

run();
