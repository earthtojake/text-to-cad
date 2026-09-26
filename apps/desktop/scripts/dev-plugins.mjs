/**
 * `electron-vite dev` with a chosen set of plugins (src/plugins/README.md):
 *
 *   npm run dev:base                 # the base app, no plugins
 *   node scripts/dev-plugins.mjs csv # the base app plus CSV
 *
 * It only sets HARDCORE_PLUGINS for the run, the same on every platform.
 */
import { spawn } from "node:child_process";

const plugins = process.argv[2] ?? "none";
const child = spawn("npx", ["electron-vite", "dev", ...process.argv.slice(3)], {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: { ...process.env, HARDCORE_PLUGINS: plugins },
});
child.on("exit", (code) => process.exit(code ?? 0));
