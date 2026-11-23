import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { DEFAULT_PANEL_WIDTH } from "./file-viewer/panelToggles.js";

// The viewer's chrome follows `docs/design-system.md`, "Two scales": type from the token scale (text-tiny,
// text-xs, text-ui, text-heading), and layout from the ONE viewer breakpoint (useViewerMobile)
// or a container query — never the window's `sm:`/`md:` breakpoints. Document content
// (markdown, code) keeps its own content styles and is not chrome.
const root = fileURLToPath(new URL(".", import.meta.url));
const CHROME = ["file-viewer", "host", "primitives", "loading", "annotation", "library", "cad-viewer", "renderers/kit", "renderers/glb", "renderers/mesh", "renderers/dxf",
  "renderers/board", "renderers/workspace", "search"];
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
// library) is a page, not chrome: the place on screen scrolls as a page does, with the platform's own scrollbar, and
// its sidebar, which is chrome (the panel's surface, `file-viewer/PanelSurface.jsx`), in the panel's ScrollArea. A
// strip that scrolls with no bar at all (the panel's tabs, `FlatPanel.jsx`: its scrollbar hidden,
// `[scrollbar-width:none]`, its clipped edge faded instead) shows no scrollbar to style.
const NATIVE_SCROLLER = /\boverflow(?:-[xy])?-(?:auto|scroll)\b/;
const PAGES = ["library/ModelLibrary.tsx"];
const SCROLL_REGIONS = ["renderers/kit/tools/ToolPanel.jsx", "primitives/dropdown-menu.jsx", "renderers/kit/status/ViewerAlertCard.jsx",
  "search/DocumentSearch.tsx", "file-viewer/PanelSurface.jsx"];

test("every scroll region in the viewer's chrome is the ScrollArea primitive, never a native scroller", () => {
  const found = [];
  for (const dir of [...CHROME, "renderers/xbf", "renderers/robot"]) for (const file of sources(join(root, dir))) {
    if (PAGES.includes(relative(root, file))) continue;
    readFileSync(file, "utf8").split("\n").forEach((line, index) => {
      if (NATIVE_SCROLLER.test(line) && !line.includes("[scrollbar-width:none]")) found.push(`${relative(root, file)}:${index + 1}: ${line.trim().slice(0, 120)}`);
    });
  }
  assert.deepEqual(found, []);
  for (const file of SCROLL_REGIONS) assert.match(readFileSync(join(root, file), "utf8"), /<ScrollArea\b/, `${file} scrolls in a ScrollArea`);
});

// The Home (`library/`) is the chrome's type scale (`docs/design-system.md`, "The type scale"): the controls and Home
// text-ui (13/20), the place's name the one larger text (15/20 semibold), a name, a project's folder and the way back
// 12/16 (text-xs), a card's facts, a format's badge, a key and the table's header 11/16 (text-tiny); a tile's glyph
// 16px. Its sidebar is the panel's own surface (`file-viewer/PanelSurface.jsx`), which sets the panel's one size itself.
test("the Home is the chrome's type scale: the place's name 15/20, names 12/16, facts 11/16, and 16px glyphs", () => {
  // Its rules, without the comments that stand before them.
  const css = readFileSync(join(root, "styles/globals.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const sizes = [...css.matchAll(/([^{}]*\.cad-library[^{}]*)\{([^}]*)\}/g)].flatMap(([, selector, body]) => {
    const size = body.match(/font-size:\s*([^;]+);/)?.[1].trim();
    return size ? [[selector.trim().replace(/\s+/g, " "), size]] : [];
  });
  assert.deepEqual(sizes, [
    [".cad-library-title", "var(--cad-text-heading)"],
    [".cad-library-path", "var(--cad-text-xs)"],
    [".cad-library-back", "var(--cad-text-xs)"],
    [".cad-library-key", "var(--cad-text-tiny)"],
    // Home, in the navbar and in the page's own bar, is the navbar's 13/20.
    [".cad-library-heading", "var(--cad-text-ui)"],
    [".cad-library-format", "var(--cad-text-tiny)"],
    [".cad-library-card .cad-library-label", "var(--cad-text-xs)"],
    [".cad-library-status", "var(--cad-text-tiny)"],
    [".cad-library-columns", "var(--cad-text-tiny)"],
    [".cad-library-row .cad-library-label", "var(--cad-text-xs)"],
    [".cad-library-welcome-title", "var(--cad-text-heading)"],
    [".cad-library-welcome-formats", "var(--cad-text-tiny)"],
  ]);
  assert.match(css, /\.cad-library-glyph \{[^}]*width: 16px; height: 16px;/);
  for (const file of ["library/ModelLibrary.tsx", "library/LibraryPlaces.jsx"]) {
    assert.deepEqual([...readFileSync(join(root, file), "utf8").matchAll(/\btext-(tiny|xs)\b/g)].map(([name]) => name), [], `${file} takes its type from the stylesheet`);
  }
  const page = readFileSync(join(root, "library/ModelLibrary.tsx"), "utf8");
  assert.match(page, /className="cad-library h-full text-ui"/);
  // The place on screen is the page: it alone scrolls with the platform's scrollbar.
  assert.match(page, /<main className="cad-library-content overflow-y-auto"/);
  assert.equal(page.match(/\boverflow(?:-[xy])?-(?:auto|scroll)\b/g).length, 1);
});

// THE type scale (`docs/design-system.md`, "The type scale"): three interface sizes and one heading, each on a fixed
// line height -- tiny 11/16, xs 12/16, ui 13/20, heading 15/20 semibold -- and a phone's each step 2px up ("Two scales":
// tiny 13/18, xs 14/20, ui 15/20, heading 17/22), the view's panel at xs (12/16; a phone's 14/20). No 10px step (text-micro is gone),
// and no stylesheet sets a font size in pixels: every size is the scale's.
test("the type scale is three sizes and a heading on fixed line heights, a phone's each 2px up, with no 10px step", () => {
  const css = readFileSync(join(root, "styles/globals.css"), "utf8"), tokens = readFileSync(join(root, "styles/tokens.css"), "utf8");
  const block = selector => css.slice(css.indexOf(`${selector} {`)).split("}")[0];
  const vars = text => Object.fromEntries([...text.matchAll(/--cad-(text|leading)-(\w+):\s*([^;]+);/g)].map(([, kind, name, value]) => [`${kind}-${name}`, value.trim()]));
  assert.deepEqual(vars(block(":root")), { "text-tiny": "0.6875rem", "text-xs": "0.75rem", "text-ui": "0.8125rem", "text-heading": "0.9375rem",
    "text-panel": "0.75rem", "leading-tiny": "1rem", "leading-xs": "1rem", "leading-ui": "1.25rem", "leading-heading": "1.25rem", "leading-panel": "1rem" });
  assert.deepEqual(vars(block(':root:has([data-viewer-layout="mobile"]:not([data-offscreen-picture] *))')), { "text-tiny": "13px", "text-xs": "14px", "text-ui": "15px", "text-heading": "17px",
    "text-panel": "14px", "leading-tiny": "18px", "leading-xs": "20px", "leading-ui": "20px", "leading-heading": "22px", "leading-panel": "20px" });
  for (const name of ["tiny", "xs", "ui", "heading"]) assert.match(tokens, new RegExp(`--text-${name}--line-height: var\\(--cad-leading-${name}\\);`));
  assert.match(tokens, /--text-heading--font-weight: 600;/);
  assert.doesNotMatch(css + tokens, /micro/);
  assert.deepEqual([...css.matchAll(/font-size:\s*\d[^;]*;/g)].map(([match]) => match), [], "no pixel or rem font size but the scale's variables");
  const found = [];
  for (const dir of [...CHROME, "renderers/xbf", "renderers/robot"]) for (const file of sources(join(root, dir))) {
    if (/\btext-micro\b/.test(readFileSync(file, "utf8"))) found.push(relative(root, file));
  }
  assert.deepEqual(found, []);
});

// Every menu, dropdown, select and context menu is the scale's xs step (12/16; a phone's 14/20), each item at least the
// row (28; a phone's 36), its shortcut hints 11px, and a tooltip the tiny step: the primitives set it, so no menu or item
// brings a size of its own.
test("menus are the xs step on the row and tooltips the tiny step, from the primitives alone", () => {
  for (const file of ["primitives/dropdown-menu.jsx", "primitives/context-menu.jsx"]) {
    const text = readFileSync(join(root, file), "utf8");
    assert.match(text, /bg-popover (p-1 )?text-xs text-popover-foreground/, `${file} draws its menu at text-xs`);
    for (const item of text.matchAll(/"[^"]*\bpy-1\.5\b[^"]*"/g)) assert.match(item[0], /min-h-row .*text-xs/, `${file}: ${item[0].slice(0, 60)}`);
    assert.doesNotMatch(text, /leading-4/, `${file}: no fixed line height`);
  }
  assert.match(readFileSync(join(root, "primitives/tooltip.jsx"), "utf8"), /text-tiny leading-\(--cad-leading-tiny\)/);
  assert.doesNotMatch(readFileSync(join(root, "renderers/kit/shell/ViewportContextMenu.jsx"), "utf8"), /DropdownMenuItem className="text-/);
});

// The logo stands on the page's gutter (`docs/viewer-ux.md`, "The navbar"): the navbar's 8px, the logo centred in its 28px tile (6px)
// and the 2px its artwork sits in put its drawn mark 16px in, over the home and a page. The Home itself is full width:
// its sidebar the viewer's panel (its surface, its 232px default width) with its content on the panel's 16px inset and
// Settings pinned at its foot, and the place on screen on 24px gutters, 20px under the navbar (12px by 16px in a narrow
// home), its tiles 232px at least.
test("the navbar's logo's drawn mark stands 16px in, and the Home is the panel's sidebar beside the place on its own gutters", () => {
  const css = readFileSync(join(root, "styles/globals.css"), "utf8");
  // The sidebar is the panel's surface, never a rule of the Home's own: its width, rule and colour are the panel's.
  assert.doesNotMatch(css, /\.cad-library-sidebar \{/);
  const sidebar = readFileSync(join(root, "library/LibrarySidebar.jsx"), "utf8");
  assert.match(sidebar, /<PanelSurface mode="push"/);
  assert.match(sidebar, /width: clampPanelWidth\(record\.width\)/);
  assert.equal(DEFAULT_PANEL_WIDTH, 232);
  // It ends in the panel's foot, the one a document's panel ends in: its rule the panel's full width, its tiles on the inset.
  assert.match(sidebar, /const foot = <PanelFoot \/>;/);
  assert.match(readFileSync(join(root, "file-viewer/PanelFoot.jsx"), "utf8"), /border-t border-border" style=\{FOOT_STYLE\} data-app-foot=""/);
  assert.match(css, /\.cad-library-places \{[^}]*padding: 8px var\(--panel-inset\) /);
  assert.match(css, /\.cad-library-content \{[^}]*flex: 1 1 0; min-width: 0; padding: 20px 24px /);
  assert.doesNotMatch(css, /\.cad-library-content \{[^}]*max-width/);
  assert.match(css, /\[data-library-narrow\] \.cad-library-content \{ padding: 12px 16px /);
  assert.match(css, /\.cad-library-grid \{[^}]*minmax\(232px, 1fr\)/);
  const navbar = readFileSync(join(root, "file-viewer/navigation/ViewerNavbar.jsx"), "utf8");
  // The row the control and 12px (40px), the tool strip's height, its icon buttons the strip's tile (the control, 28px):
  // THE scale's (a phone's from the same tokens).
  const row = readFileSync(join(root, "lib/navbarRow.js"), "utf8");
  assert.match(row, /NAVBAR_ROW_CLASS = "flex h-\[calc\(var\(--cad-control\)\+12px\)\] shrink-0 items-center gap-2 border-b px-2"/);
  assert.match(row, /NAVBAR_CONTROL_CLASS = "size-control /);
  assert.match(navbar, /cn\(NAVBAR_ROW_CLASS, "relative border-border /);
  assert.match(navbar, /"cad-navbar-logo w-control justify-start px-\[calc\(\(var\(--cad-control\)-16px\)\/2\)\]"/);
  assert.match(navbar, /const NAV_ITEM_CLASS = "flex h-control /);
});

// The panel's rows have ONE owner of their horizontal geometry (`docs/design-system.md`, "Spacing and the panel inset"): the row
// primitive pads a row by its `depth` and draws its guides, and the view's panel sets the lines. No
// list pads a row, nor brings its own glyph column or chevron: only the primitive reads the old constants.
const ROW_OWNERS = ["primitives/tree-row.jsx"];
const ROW_CONSTANTS = /\b(TREE_ROW_INSET_PX|TREE_INDENT_PX|LAYER_ROW_INSET_PX|TreeRowGuides)\b/;
const ROW_PADDING = /padding(?:Left|Right|Inline|InlineStart|InlineEnd)?\b|(?<![\w-])p[lrxse]?-/;
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

// A number a slider sets is the ONE slider control (`docs/design-system.md`, "The slider control"): its
// label, its number field and its slider. Only it and the playback scrubber (the tools view's playbar's and Preview's), a timeline, draw the
// slider primitive; no site brings its own slider and number.
const SLIDER_OWNERS = ["renderers/kit/inspector/SliderField.jsx", "renderers/kit/tools/playbar/AnimationTimeControl.js"];
// The primitive's module by any spelling (`@cad/ui/primitives/slider`, `../primitives/slider.jsx`), or
// Radix's slider under it, which only the primitive itself wraps.
const SLIDER_IMPORT = /primitives\/slider(?:\.jsx)?["'/]|@radix-ui\/react-slider/;
test("only the slider control and the scrubber import the slider primitive", () => {
  const found = sources(root).map(file => relative(root, file))
    .filter(name => ![...SLIDER_OWNERS, "primitives/slider.jsx"].includes(name) && SLIDER_IMPORT.test(readFileSync(join(root, name), "utf8")));
  assert.deepEqual(found, []);
});

// A size of the scale given to a primitive replaces the primitive's own (a button's text-xs), and
// survives a colour after it: cn() knows the scale's names as sizes.
test("cn() merges the scale's sizes as font sizes", async () => {
  const { cn } = await import("./lib/utils.js");
  assert.equal(cn("h-6 text-xs", "text-ui"), "h-6 text-ui");
  assert.equal(cn("text-tiny", "text-muted-foreground"), "text-tiny text-muted-foreground");
  assert.equal(cn("text-ui", "text-foreground"), "text-ui text-foreground");
  assert.equal(cn("text-xs", "text-heading"), "text-heading");
});
