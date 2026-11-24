#!/usr/bin/env node
// Copy the viewer's built client into ./viewer, the Worker's static assets (wrangler.jsonc).
//
//   npm run build:web                  # at the repository root: the viewer, into apps/web/dist
//   npm --prefix apps/share run build  # this: apps/web/dist -> apps/share/viewer
//   node apps/share/build.mjs [--from DIR]
//
// The source maps stay behind: nothing on the page names them, and they are not served.

import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const here = dirname(fileURLToPath(import.meta.url));
const { values } = parseArgs({ options: { from: { type: "string", default: join(here, "..", "web", "dist") } } });
const from = resolve(values.from);
const to = join(here, "viewer");

if (!existsSync(join(from, "index.html"))) {
  console.error(`No built viewer at ${from}: run \`npm run build:web\` at the repository root first.`);
  process.exit(1);
}
rmSync(to, { recursive: true, force: true });
cpSync(from, to, { recursive: true, filter: (source) => !source.endsWith(".map") });
console.log(`Copied the viewer into ${to}`);
