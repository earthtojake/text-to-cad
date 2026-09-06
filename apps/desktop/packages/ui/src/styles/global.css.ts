/**
 * global.css.ts — single side-effect barrel for the full @emdash/ui VE style stack.
 *
 * Import this once in your app entry to pull every VE module into the build graph
 * so their globalStyle output lands in dist/style.css.
 *
 * Layer order (lower → higher priority):
 *   reset < tokens < base < recipes < utilities
 *
 * Plain CSS files (theme.css, semantic.css, theme.base.css, typography,
 * overflow-fade) must still be @imported in the host's CSS pipeline.
 *
 * Usage:
 *   import '@emdash/ui/styles/global';  // in app entry or Storybook preview
 */

// 1. Layer order must be declared first.
export * from './layers.css';

// 2. Non-color design tokens (:root custom properties).
export * from '../theme/tokens.css';

// 3. Surface cascade scope classes (.surface-*).
export * from './surfaces.css';

// 4. Mini-preflight (reset layer).
export * from './reset.css';

// 5. Global element defaults (body, scrollbars, selection) are now opt-in.
// Import '@emdash/ui/styles/global-base.css' in the host app or Storybook
// preview when you want these element defaults. They are NOT included here
// so they don't fight the host app's own body/token CSS.

// 6. Atomic utility classes — sx() sprinkles (utilities layer).
export * from './utilities/sprinkles.css';

// 7. VE animation keyframes used by overlay primitives.
export * from './effects/animations.css';

// 8. SVG helper classes.
export * from './effects/svg-helpers.css';
