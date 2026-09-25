import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// The viewer's chrome follows docs/settings-ui.md: type from the token scale (text-micro,
// text-tiny, text-xs, text-ui), and layout from the ONE viewer breakpoint (useViewerMobile)
// or a container query — never the window's `sm:`/`md:` breakpoints. Document content
// (markdown, code) keeps its own content styles and is not chrome.
const root = fileURLToPath(new URL(".", import.meta.url));
const CHROME = ["file-viewer", "host", "primitives", "loading", "drawing", "renderers/kit", "renderers/glb", "renderers/mesh", "renderers/dxf",
  "renderers/image", "renderers/workspace", "renderers/pdf", "renderers/unsupported"];
const sources = dir => readdirSync(dir).flatMap(name => {
  const path = join(dir, name);
  if (statSync(path).isDirectory()) return name === "__fixtures__" ? [] : sources(path);
  return /\.(jsx?|tsx?)$/.test(name) && !/\.test\./.test(name) ? [path] : [];
});
const WINDOW_BREAKPOINT = /(^|[\s"'`])(sm|md|lg|xl|2xl):[\w[!-]/;
const PIXEL_FONT_SIZE = /\btext-\[\d+(\.\d+)?px\]/;

test("viewer chrome uses the type scale and the viewer breakpoint, never window breakpoints or pixel font sizes", () => {
  const found = [];
  for (const dir of CHROME) for (const file of sources(join(root, dir))) {
    readFileSync(file, "utf8").split("\n").forEach((line, index) => {
      if (WINDOW_BREAKPOINT.test(line) || PIXEL_FONT_SIZE.test(line)) found.push(`${relative(root, file)}:${index + 1}: ${line.trim().slice(0, 120)}`);
    });
  }
  assert.deepEqual(found, []);
});
