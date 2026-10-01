import { describe, expect, it } from "vitest";

/**
 * Two keyboard traps the sweep found by eye, held by a scan of every renderer component:
 *
 * 1. A control revealed on hover (`opacity-0 group-hover:opacity-100`) that has no focus twin
 *    (`focus-visible:opacity-100` or `group-focus-within:opacity-100`) is invisible while the
 *    keyboard is on it. Named groups (`group-hover/row:opacity-100`) count.
 * 2. A `<button>`, `<Button>` or `role="button"` that removes the outline (`outline-none`,
 *    `outline-hidden`, with or without a variant in front) and draws no focus-scoped ring,
 *    outline or shadow of its own (`focus-visible:ring-2`, `focus:ring`, `focus-visible:outline-2`,
 *    `focus-visible:shadow-…`) has no visible focus at all. A `focus-visible:bg-accent` is a tint,
 *    not a ring, and `hover:ring-2` is not focus; neither counts. The one indirect form allowed is
 *    a parent ring on the same file (`has-[…:focus-visible]:ring-…`), which the scan cannot tie to
 *    a particular button, so a file with one is taken as a whole.
 *
 * The scan reads source text, so it knows class strings and opening tags, not what a parent
 * merges over them. Where the override lives elsewhere, the entry is in ALLOWED with the reason.
 */
const sources = import.meta.glob("../../../src/renderer/**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

type Site = { at: string; file: string; text: string };

/**
 * A site is excused by its file and a short snippet of the text it was found in (a class string,
 * or an opening tag), not by a line number: an edit above it does not turn the entry stale, and
 * a different site in the same file is not excused by it. `count` is how many sites it covers.
 * A fixed site comes off the list; an entry that no longer matches fails.
 */
const ALLOWED: { file: string; snippet: string; count?: number; reason: string }[] = [
  {
    file: "components/ai-elements/attachments.tsx",
    snippet: "opacity-0 transition-opacity group-hover:opacity-100",
    count: 2,
    reason: "the grid and inline remove buttons are overridden at Composer.tsx (opacity-60, focus-visible:opacity-100 and a ring)",
  },
  {
    file: "features/explorer/TabStrip.tsx",
    snippet: "aria-label={`Close ${title}`}",
    reason: "the tab's close button is aria-hidden and outside the Tab order (Delete on the tab is its keyboard twin), so keyboard focus never lands on it",
  },
  {
    file: "components/ai-elements/prompt-input.tsx",
    snippet: 'title="Upload files"',
    reason: "the hidden file input (`className=\"hidden\"`) is never seen or hovered; the title is its accessible name beside the aria-label",
  },
  {
    file: "components/ai-elements/web-preview.tsx",
    snippet: 'title="Preview"',
    reason: "an iframe's `title` is its accessible name, not a hover hint; and `WebPreviewBody`, the iframe, is vendored and unused (`WebPreview` and `WebPreviewNavigation` are used by `features/explorer/BrowserTab.tsx`)",
  },
  {
    file: "components/ui/sidebar.tsx",
    snippet: 'title="Toggle Sidebar"',
    reason: "SidebarRail is vendored and unused (the app's sidebar has its own toggle, hinted by TooltipHint)",
  },
];

const allowed = (site: Site) => ALLOWED.some((entry) => entry.file === site.file && site.text.includes(entry.snippet));

/** `src/renderer/` onward, and the 1-based line of `offset`. */
const fileOf = (path: string) => path.replace(/^.*\/src\/renderer\//, "");
const where = (path: string, source: string, offset: number) =>
  `${fileOf(path)}:${source.slice(0, offset).split("\n").length}`;
const site = (path: string, source: string, offset: number, text: string): Site => ({
  at: where(path, source, offset),
  file: fileOf(path),
  text,
});

/** The opening tag starting at `start` (a `<`), through its closing `>` outside any `{…}` or string. */
function openingTag(source: string, start: number): string {
  let depth = 0;
  let quote: string | null = null;
  for (let i = start; i < source.length; i += 1) {
    const ch = source[i]!;
    if (quote) {
      if (ch === "\\") i += 1;
      else if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'" || ch === "`") quote = ch;
    else if (ch === "{") depth += 1;
    else if (ch === "}") depth -= 1;
    else if (ch === ">" && depth === 0 && source[i - 1] !== "=") return source.slice(start, i + 1);
  }
  return source.slice(start);
}

/** Every string literal that looks like a class list, with its offset. */
function* classStrings(source: string): Generator<{ text: string; offset: number }> {
  for (const match of source.matchAll(/"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`/g)) {
    yield { text: match[1] ?? match[2] ?? match[3] ?? "", offset: match.index };
  }
}

const tokens = (text: string) => text.split(/\s+/);

/** `group-hover:opacity-100`, `group-hover/row:opacity-100`. */
const HOVER_REVEAL = /^group-hover(?:\/[\w-]+)?:opacity-100$/;
/** The keyboard's twin of it, on the element itself or on a named group or peer. */
const FOCUS_REVEAL = /^(?:focus-visible|focus-within|focus|group-focus-within|group-focus-visible|group-focus|peer-focus-visible|peer-focus)(?:\/[\w-]+)?:opacity-100$/;

function hoverOnlyReveals(path: string, source: string): Site[] {
  const found: Site[] = [];
  for (const { text, offset } of classStrings(source)) {
    const list = tokens(text);
    if (!list.includes("opacity-0") || !list.some((t) => HOVER_REVEAL.test(t))) continue;
    if (list.some((t) => FOCUS_REVEAL.test(t))) continue;
    found.push(site(path, source, offset, text));
  }
  return found;
}

/** An outline removed, bare or behind variants (`outline-none`, `focus-visible:outline-none`). */
const OUTLINE_REMOVED = /(?:^|[\s"'`(,])(?:[^\s"'`]*:)?!?outline-(?:none|hidden)(?![\w-])/;
/**
 * A class that draws something under focus: a ring with a width (`ring`, `ring-2`, `ring-[3px]`,
 * not `ring-0`, `ring-ring/50` or `ring-offset-2`), an outline with one, or a shadow — behind a
 * variant chain that says focus (`focus-visible:`, `focus:`, `group-focus-visible:`, a
 * `has-[…:focus-visible]:` on the element itself …).
 */
const FOCUS_VARIANT = /(?:^|:)(?:focus-visible|focus|group-focus-visible|group-focus|peer-focus-visible|peer-focus|focus-within|has-\[[^\]\s]*focus[^\]\s]*\]|\[&:focus[^\]\s]*\])(?:\/[\w-]+)?:/;
const DRAWS = /^!?(?:ring(?:-(?:[1-9]\d*|\[\d[^\]]*\]|inset))?|outline(?:-(?:[1-9]\d*|\[\d[^\]]*\]|solid|dashed|dotted|double))?|shadow(?:-(?!none)[\w/[\]().-]+)?)(?:\/[\w-]+)?$/;
const drawsFocus = (text: string) =>
  text.split(/[\s"'`]+/).some((t) => FOCUS_VARIANT.test(t) && DRAWS.test(t.slice(t.lastIndexOf(":") + 1)));
/**
 * A ring drawn by a parent around a button it holds (`has-[:focus-visible]:ring-2`). The scan
 * cannot say which button the parent holds, so a file with one excuses the file's outline-less buttons.
 */
const PARENT_RING = /has-\[[^\]\s]*focus-visible[^\]\s]*\]:(?:ring|outline|shadow)/;

function ringlessButtons(path: string, source: string): Site[] {
  const found: Site[] = [];
  const starts = new Set<number>();
  for (const match of source.matchAll(/<(?:button|Button)\b/g)) starts.add(match.index);
  for (const match of source.matchAll(/role="button"/g)) {
    const start = source.lastIndexOf("<", match.index);
    if (start >= 0) starts.add(start);
  }
  const parentRing = PARENT_RING.test(source);
  for (const start of starts) {
    const tag = openingTag(source, start);
    if (!OUTLINE_REMOVED.test(tag)) continue;
    if (drawsFocus(tag) || parentRing) continue;
    found.push(site(path, source, start, tag));
  }
  return found;
}

/**
 * A native `title` on an element: a plain tag (`<span title=…>`) or one of the components that
 * spread their props onto a plain element (`Attachment` is a div, `DialogTitle` a heading). A
 * component's own `title` prop is not one — `ComposerChip`'s and `RowButton`'s end up in a
 * `TooltipHint` — so only these tags are read. An svg's `<title>` child is not an attribute.
 */
const SPREADS_TITLE = ["Attachment", "DialogTitle", "DialogDescription"];
const NATIVE_TITLE = new RegExp(`<(?:[a-z][a-z0-9]*|${SPREADS_TITLE.join("|")})(?=[\\s>/])`, "g");

function nativeTitles(path: string, source: string): Site[] {
  const found: Site[] = [];
  for (const match of source.matchAll(NATIVE_TITLE)) {
    const tag = openingTag(source, match.index);
    if (/(?:^|\s)title=/.test(tag.replace(/\{[^{}]*\}|"[^"]*"|'[^']*'|`[^`]*`/g, (part) => (part.startsWith("{") ? "{}" : '""')) .replace(/^<\S+/, ""))) {
      found.push(site(path, source, match.index, tag));
    }
  }
  return found;
}

function scan(find: (path: string, source: string) => Site[]): Site[] {
  return Object.entries(sources).flatMap(([path, source]) => find(path, source));
}

describe("keyboard focus is visible (source scan of src/renderer)", () => {
  const at = (sites: Site[]) => sites.map((found) => found.at);

  it("the scan itself sees the patterns it is looking for", () => {
    expect(at(hoverOnlyReveals("a.tsx", '<i className="opacity-0 group-hover:opacity-100" />'))).toEqual(["a.tsx:1"]);
    expect(at(hoverOnlyReveals("a.tsx", '<i className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100" />'))).toEqual([]);
    // Named groups are groups too, and their twin is a named one or the element's own.
    expect(at(hoverOnlyReveals("a.tsx", '<i className="opacity-0 group-hover/row:opacity-100" />'))).toEqual(["a.tsx:1"]);
    expect(at(hoverOnlyReveals("a.tsx", '<i className="opacity-0 group-hover/row:opacity-100 group-focus-within/row:opacity-100" />'))).toEqual([]);

    expect(at(ringlessButtons("a.tsx", '<button className="outline-none hover:bg-accent" />'))).toEqual(["a.tsx:1"]);
    expect(at(ringlessButtons("a.tsx", '<Button className={cn("outline-none", on && "x")} onClick={() => go()}>'))).toEqual(["a.tsx:1"]);
    expect(at(ringlessButtons("a.tsx", '<div role="button" className="outline-none focus-visible:ring-2" />'))).toEqual([]);
    // A prefixed removal is a removal.
    expect(at(ringlessButtons("a.tsx", '<button className="focus-visible:outline-none" />'))).toEqual(["a.tsx:1"]);
    expect(at(ringlessButtons("a.tsx", '<button className="md:focus:outline-hidden" />'))).toEqual(["a.tsx:1"]);
    // A tint is not a ring, and hover is not focus.
    expect(at(ringlessButtons("a.tsx", '<button className="outline-none focus-visible:bg-accent" />'))).toEqual(["a.tsx:1"]);
    expect(at(ringlessButtons("a.tsx", '<button className="outline-none hover:ring-2" />'))).toEqual(["a.tsx:1"]);
    expect(at(ringlessButtons("a.tsx", '<button className="outline-none ring-2" />'))).toEqual(["a.tsx:1"]);
    expect(at(ringlessButtons("a.tsx", '<button className="outline-none focus-visible:ring-0" />'))).toEqual(["a.tsx:1"]);
    // A width is what draws it: a colour alone draws nothing.
    expect(at(ringlessButtons("a.tsx", '<button className="outline-none focus-visible:ring-ring/50" />'))).toEqual(["a.tsx:1"]);
    // What does draw: the kit's ring, focus: forms, outlines and shadows, a ring of a group's focus.
    for (const ok of [
      "focus-visible:ring-[3px] focus-visible:ring-ring/50",
      "focus:ring-2",
      "focus-visible:outline-2",
      "focus-visible:shadow-md",
      "group-focus-visible:ring-2",
      "[&:focus-visible]:ring-2",
    ]) {
      expect(at(ringlessButtons("a.tsx", `<button className="outline-none ${ok}" />`)), ok).toEqual([]);
    }
    // A parent's ring on the same file excuses the file.
    expect(at(ringlessButtons("a.tsx", '<span className="has-[:focus-visible]:ring-2"><button className="outline-none" /></span>'))).toEqual([]);
  });

  it("no control is revealed on hover alone", () => {
    const hits = at(scan(hoverOnlyReveals).filter((found) => !allowed(found)));
    expect(hits, "add a focus-visible:opacity-100 (or group-focus-within:opacity-100) beside group-hover:opacity-100").toEqual([]);
  });

  it("no button removes its outline without drawing a ring", () => {
    const hits = at(scan(ringlessButtons).filter((found) => !allowed(found)));
    expect(hits, "add focus-visible:ring-[3px] focus-visible:ring-ring/50 (the kit's button ring)").toEqual([]);
  });

  it("the scan sees a native title on a plain tag or a spreading component, and only there", () => {
    expect(at(nativeTitles("a.tsx", '<span className="x" title={uri}>a</span>'))).toEqual(["a.tsx:1"]);
    expect(at(nativeTitles("a.tsx", '<Attachment data={f} title={f.filename}>'))).toEqual(["a.tsx:1"]);
    expect(at(nativeTitles("a.tsx", '<img\n alt=""\n title={image.name}\n/>'))).toEqual(["a.tsx:1"]);
    expect(at(nativeTitles("a.tsx", '<Chip title={project?.path} />'))).toEqual([]);
    expect(at(nativeTitles("a.tsx", '<span aria-label="a title=b">x</span>'))).toEqual([]);
  });

  it("no element carries a native title (the hint is the kit's TooltipHint)", () => {
    const hits = at(scan(nativeTitles).filter((found) => !allowed(found)));
    expect(hits, "wrap it in <TooltipHint content=…> from @text-to-cad/ui/primitives/tooltip; a native title cannot be styled and reads twice").toEqual([]);
  });

  it("every allowlist entry still matches exactly the sites it counts", () => {
    const live = [...scan(hoverOnlyReveals), ...scan(ringlessButtons), ...scan(nativeTitles)];
    const stale = ALLOWED.filter(
      (entry) => live.filter((found) => found.file === entry.file && found.text.includes(entry.snippet)).length !== (entry.count ?? 1),
    );
    expect(stale.map((entry) => `${entry.file}: ${entry.snippet}`)).toEqual([]);
  });
});
