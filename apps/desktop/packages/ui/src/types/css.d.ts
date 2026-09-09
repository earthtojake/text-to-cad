/**
 * Ambient type declaration for plain CSS file imports.
 *
 * Allows TypeScript to accept side-effect imports of plain .css files
 * (e.g. `import '@styles/theme.base.css'`) in .tsx/.ts source files.
 * The actual bundling is handled by Vite (dev/Storybook) and the VE
 * plugin's CSS extraction pipeline (lib build → dist/style.css).
 */
declare module '*.css' {
  const classes: Record<string, string>;
  export = classes;
}
