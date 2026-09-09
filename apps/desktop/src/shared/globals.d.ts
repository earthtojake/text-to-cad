/** Build-time constants, defined by electron.vite.config.ts in every target. */

/** The repository's VERSION at build time (see scripts/app-version.mjs). */
declare const __APP_VERSION__: string;

/**
 * The Aptabase project key, from `HARDCORE_APTABASE_KEY` at build time. Empty
 * in every build that was not given one, which makes telemetry inert. Defined
 * for the main process only — telemetry never runs in the renderer.
 */
declare const __APTABASE_KEY__: string;
