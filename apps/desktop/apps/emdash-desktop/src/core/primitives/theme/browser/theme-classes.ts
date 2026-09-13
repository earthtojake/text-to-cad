/**
 * Canonical theme class names shared by the app's theme system and
 * @emdash/theme's generated selectors.
 *
 * The canonical product values in design-system.css and the generated --em-*
 * vars from @emdash/theme key off the SAME class on <html>, so a single
 * classList write themes both systems atomically. The values here must
 * stay equal to the THEME_MANIFEST selectors in
 * packages/theme/src/themes/registry.ts — theme-classes.test.ts enforces it.
 *
 * The pre-paint script in src/renderer/index.html cannot import this module
 * and hardcodes the same literals; the test covers that file too.
 */
export const THEME_CLASS_LIGHT = 'emlight';
export const THEME_CLASS_DARK = 'emdark';
export const THEME_CLASSES = [THEME_CLASS_LIGHT, THEME_CLASS_DARK] as const;

/** localStorage key the pre-paint script reads to avoid a theme flash. */
export const THEME_STORAGE_KEY = 'hardcore-theme';
