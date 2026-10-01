/**
 * A rehype plugin that spells a bare relative image source — `render.png`,
 * `renders/front.png` — the one way rehype-harden admits: `./render.png`.
 *
 * Harden parses a source against no origin, so a path with no `./`, `/` or
 * `../` in front is unparseable to it and becomes `[Image blocked: …]`
 * before the transcript's `img` (`TranscriptImage`) is asked — a project
 * render the agent names the way it names any file never drew. With the
 * `./`, harden hands it on as `/render.png`, which `pathTarget` reads back as
 * the project path; whether it exists and is an image stays that
 * component's question. It runs after the sanitizer and before harden, and
 * touches nothing with a scheme or a host: an `https:` or `data:` source
 * reaches harden and the component exactly as before.
 *
 * `remarkPathLinks` does the same for a link's URL, in the markdown tree; an
 * image can also arrive as raw `<img>` HTML, which only this tree has.
 */
type HastNode = {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
};

const SCHEME = /^[a-z][a-z0-9+.-]*:/i;

export function rehypeProjectImages() {
  return (tree: HastNode) => {
    walk(tree);
  };
}

function walk(node: HastNode): void {
  if (node.type === "element" && node.tagName === "img" && node.properties) {
    const src = node.properties.src;
    if (typeof src === "string" && isBareRelative(src)) {
      node.properties.src = `./${src}`;
    }
  }
  for (const child of node.children ?? []) {
    walk(child);
  }
}

function isBareRelative(src: string): boolean {
  return src !== "" && !SCHEME.test(src) && !/^(\/|\.\/|\.\.\/|#)/.test(src);
}
