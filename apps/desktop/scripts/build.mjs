/**
 * `npm run build`: everything a runnable `out/` needs, in order.
 *
 *   1. compose the Hardcore plugin into resources/plugin (build-plugin.mjs);
 *   2. electron-vite build — main, preload, renderer into out/;
 *   3. bundle the MCP server into out/hardcore-mcp (build-mcp.mjs), after
 *      electron-vite because it empties its output directories first.
 *
 * `scripts/package.mjs` runs this before electron-builder, so a packaged app
 * and the app the e2e suite launches are built the same way.
 */
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { appVersion } from "./app-version.mjs";
import { buildMcpServer } from "./build-mcp.mjs";
import { buildPlugin } from "./build-plugin.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");

export function buildAll({ env = process.env } = {}) {
  const version = appVersion();

  const plugin = buildPlugin({ repoRoot, out: path.join(appRoot, "resources", "plugin"), version });
  console.info(`composed plugin cad@hardcore ${plugin.version} (${plugin.skills.length} skills)`);

  const npx = process.platform === "win32" ? "npx.cmd" : "npx";
  const result = spawnSync(npx, ["electron-vite", "build"], { cwd: appRoot, stdio: "inherit", env });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }

  return buildMcpServer({ version }).then((mcp) => {
    console.info(`bundled hardcore-mcp ${mcp.version} -> ${path.relative(appRoot, mcp.out)}`);
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await buildAll();
}
