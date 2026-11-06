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
const CHROME = ["file-viewer", "host", "primitives", "loading", "annotation", "library", "cad-viewer", "renderers/kit", "renderers/glb", "renderers/mesh", "renderers/dxf",
  "renderers/board", "renderers/workspace"];
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

// Every scroll region of the chrome is the one ScrollArea primitive (`primitives/scroll-area.jsx`):
// thin overlay bars in the theme's colours, never the platform's scrollbar. The home (the model
// library) is a page, not chrome: it scrolls as a page does, with the platform's own scrollbar.
const NATIVE_SCROLLER = /\boverflow(?:-[xy])?-(?:auto|scroll)\b/;
const PAGES = ["library/ModelLibrary.tsx"];
const SCROLL_REGIONS = ["renderers/kit/tools/ToolPanel.jsx", "file-viewer/navigation/FolderExplorer.jsx", "primitives/dropdown-menu.jsx",
  "renderers/kit/status/ViewerAlertCard.jsx"];

test("every scroll region in the viewer's chrome is the ScrollArea primitive, never a native scroller", () => {
  const found = [];
  for (const dir of [...CHROME, "renderers/xbf", "renderers/robot"]) for (const file of sources(join(root, dir))) {
    if (PAGES.includes(relative(root, file))) continue;
    readFileSync(file, "utf8").split("\n").forEach((line, index) => {
      if (NATIVE_SCROLLER.test(line)) found.push(`${relative(root, file)}:${index + 1}: ${line.trim().slice(0, 120)}`);
    });
  }
  assert.deepEqual(found, []);
  for (const file of SCROLL_REGIONS) assert.match(readFileSync(join(root, file), "utf8"), /<ScrollArea\b/, `${file} scrolls in a ScrollArea`);
});

// The Home (`library/`) is one type scale (docs/settings-ui.md): every text text-ui, 13px -- the
// type filter, the search, the names, the table, its header included -- but the heading, Recent, the
// one larger text (17px, the owner's exception), and a tile's age, text-tiny and muted; a tile's and
// a row's glyph 16px.
test("the Home is one type scale: text-ui throughout but the heading and a tile's age, and 16px glyphs", () => {
  const css = readFileSync(join(root, "styles/globals.css"), "utf8");
  const sizes = [...css.matchAll(/([^{}]*\.cad-library[^{}]*)\{([^}]*)\}/g)].flatMap(([, selector, body]) => {
    const size = body.match(/font-size:\s*([^;]+);/)?.[1].trim();
    return size ? [[selector.trim().replace(/\s+/g, " "), size]] : [];
  });
  assert.deepEqual(sizes, [
    [".cad-library-heading", "1.0625rem"],
    [".cad-library-status", "var(--text-tiny, 0.6875rem)"],
    [".cad-library-columns", "var(--text-ui)"],
    [".cad-library-row .cad-library-status", "var(--text-ui)"],
  ]);
  assert.match(css, /\.cad-library-glyph \{[^}]*width: 16px; height: 16px;/);
  const page = readFileSync(join(root, "library/ModelLibrary.tsx"), "utf8");
  assert.deepEqual([...page.matchAll(/\btext-(micro|tiny|xs)\b/g)].map(([name]) => name), []);
  assert.match(page, /className="cad-library h-full overflow-y-auto text-ui"/);
});

// The logo stands on the page's gutter (docs/settings-ui.md): the navbar's 10px start, the logo
// button's 4px padding and the 2px its artwork sits in put its drawn mark 16px in, over the home and a page. The Home itself is a centred
// column of its own, 1128px at most on 24px gutters, 44px under the navbar, its tiles 280px at least.
test("the navbar's logo's drawn mark stands 16px in, and the Home is a centred 1128px column on its own gutters", () => {
  const css = readFileSync(join(root, "styles/globals.css"), "utf8");
  assert.match(css, /\.cad-library-content \{[^}]*max-width: 1128px; margin: 0 auto; padding: 44px 24px /);
  assert.match(css, /\.cad-library-grid \{[^}]*minmax\(280px, 1fr\)/);
  const navbar = readFileSync(join(root, "file-viewer/navigation/ViewerNavbar.jsx"), "utf8");
  // 10px, the button's 4px, and the 2px the mark's artwork sits in from its image's edge.
  assert.match(navbar, /cn\(NAVBAR_ROW_CLASS, "pl-\[10px\] /);
  assert.match(navbar, /"cad-navbar-logo justify-start px-1"/);
});

// The panel's rows have ONE owner of their horizontal geometry (docs/settings-ui.md): the row
// primitive pads a row by its `depth` and draws its guides, and the view's panel sets the lines. No
// list pads a row, nor brings its own glyph column or chevron: only the primitive and the explorer
// (which pads its own rows) read the old constants.
const ROW_OWNERS = ["primitives/tree-row.jsx", "file-viewer/navigation/FolderExplorer.jsx", "file-viewer/navigation/ModelList.jsx"];
const ROW_CONSTANTS = /\b(TREE_ROW_INSET_PX|TREE_INDENT_PX|LAYER_ROW_INSET_PX|TreeRowGuides)\b/;
const ROW_PADDING = /paddingLeft|paddingInline|(?<![\w-])p[lx]-/;
// The opening tag at `from`, to its closing `>`: braces and quotes skipped.
const openingTag = (text, from) => {
  let depth = 0, quote = "";
  for (let at = from + 1; at < text.length; at += 1) {
    const char = text[at];
    if (quote) { if (char === quote) quote = ""; continue; }
    if (char === "\"" || char === "'" || char === "`") quote = char;
    else if (char === "{") depth += 1;
    else if (char === "}") depth -= 1;
    else if (char === ">" && depth === 0) return text.slice(from, at + 1);
  }
  return text.slice(from);
};

test("a panel row is padded by the row primitive alone: no list pads one, reads the old insets, or draws its own chevron", () => {
  const found = [];
  for (const file of sources(root)) {
    const name = relative(root, file);
    if (ROW_OWNERS.includes(name)) continue;
    const text = readFileSync(file, "utf8");
    if (ROW_CONSTANTS.test(text)) found.push(`${name}: ${text.match(ROW_CONSTANTS)[1]}`);
    if (name.startsWith("renderers/") && /\bTreeRowChevron\b/.test(text)) found.push(`${name}: TreeRowChevron`);
    for (const match of text.matchAll(/<TreeRowSurface\b/g)) {
      const tag = openingTag(text, match.index);
      if (ROW_PADDING.test(tag)) found.push(`${name}: ${tag.replace(/\s+/g, " ").slice(0, 120)}`);
    }
  }
  assert.deepEqual(found, []);
});

// A number a slider sets is the ONE slider control (docs/settings-ui.md, "The slider control"): its
// label, its quiet value and its slider. Only it and the playbar's scrubber, a timeline, draw the
// slider primitive; no site brings its own slider and number.
const SLIDER_OWNERS = ["renderers/kit/inspector/SliderField.jsx", "renderers/kit/tools/playbar/AnimationTimeControl.js"];
test("only the slider control and the scrubber import the slider primitive", () => {
  const found = sources(root).map(file => relative(root, file))
    .filter(name => !SLIDER_OWNERS.includes(name) && /primitives\/slider["'/]/.test(readFileSync(join(root, name), "utf8")));
  assert.deepEqual(found, []);
});

// A size of the scale given to a primitive replaces the primitive's own (a button's text-xs), and
// survives a colour after it: cn() knows the scale's names as sizes.
test("cn() merges the scale's sizes as font sizes", async () => {
  const { cn } = await import("./lib/utils.js");
  assert.equal(cn("h-6 text-xs", "text-ui"), "h-6 text-ui");
  assert.equal(cn("text-tiny", "text-muted-foreground"), "text-tiny text-muted-foreground");
  assert.equal(cn("text-ui", "text-foreground"), "text-ui text-foreground");
});
