/**
 * global.css.ts — aggregated side-effect entry point for VE styles.
 *
 * Imported by index.tsx (replacing tailwind.css) once Phase 4 is complete.
 * Also used by contract-setup.ts and .storybook/preview.tsx.
 *
 * Import order matters for cascade precedence:
 *   1. reset   — box-sizing and margin resets (lowest specificity)
 *   2. theme   — :where() variable defaults (zero specificity)
 *   3. effects — keyframe definitions
 *
 * Each import is a side-effect: the VE plugin processes the .css.ts files and
 * emits their CSS into the bundle.
 */

// Side-effect imports — each file emits CSS via VE globalStyle / createGlobalTheme.
import './reset.css';
import './theme.css';
import './effects.css';
