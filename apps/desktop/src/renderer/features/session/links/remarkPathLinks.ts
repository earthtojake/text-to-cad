import { ABSOLUTE_MARK, findPathTokens, pathToken } from "./grammar";

/**
 * A remark plugin that turns path-shaped tokens in prose into links.
 *
 * Runs on the mdast Streamdown builds for every text part of an agent's
 * turn. A `text` node with `models/bracket.step#o1.2` in it becomes
 * text · link · text; an `inlineCode` node whose whole value is a path —
 * the way agents usually write one — becomes a link wrapping the code. The
 * link's URL is the token itself with a `./` in front, which is the one
 * spelling every stage downstream leaves alone: rehype-harden admits a
 * path-relative URL (a bare `models/x` it blocks as unparseable), the
 * sanitizer keeps a relative `href`, and the renderer's `a` component
 * (`PathLink.tsx`) reads the path back out of it. Whether the path exists —
 * whether it is a link at all — is that component's question, not this
 * plugin's: the tree is built once per block and cached, and an answer
 * that arrives later must not mean rebuilding it.
 *
 * Hand-rolled tree walk rather than `unist-util-visit`: it is a transitive
 * dependency here, and the walk is twelve lines.
 */
type MdNode = {
  type: string;
  value?: string;
  url?: string;
  children?: MdNode[];
  data?: Record<string, unknown>;
};

/** Where a path in prose should not become a link: it already is one, or it is code. */
const OPAQUE = new Set(["link", "linkReference", "definition", "code", "html", "image", "imageReference"]);

/**
 * `rootPath` is the thread's root on disk: a root with a space or another
 * character a path in prose is not made of is still recognised where an
 * absolute path begins with it.
 */
export function remarkPathLinks({ rootPath }: { rootPath?: string | null } = {}) {
  return (tree: MdNode) => {
    walk(tree, rootPath ?? null);
  };
}

function walk(node: MdNode, rootPath: string | null): void {
  if (!node.children) {
    return;
  }
  const next: MdNode[] = [];
  for (const child of node.children) {
    if (child.type === "text" && typeof child.value === "string") {
      next.push(...splitText(child.value, rootPath));
    } else if (child.type === "inlineCode" && typeof child.value === "string") {
      const token = pathToken(child.value, rootPath);
      next.push(token ? linkFor(token.raw, [child]) : child);
    } else {
      if (!OPAQUE.has(child.type)) {
        walk(child, rootPath);
      }
      next.push(child);
    }
  }
  node.children = next;
}

function splitText(value: string, rootPath: string | null): MdNode[] {
  const tokens = findPathTokens(value, rootPath);
  if (tokens.length === 0) {
    return [{ type: "text", value }];
  }
  const nodes: MdNode[] = [];
  let at = 0;
  for (const token of tokens) {
    if (token.start > at) {
      nodes.push({ type: "text", value: value.slice(at, token.start) });
    }
    nodes.push(linkFor(token.raw, [{ type: "text", value: token.raw }]));
    at = token.end;
  }
  if (at < value.length) {
    nodes.push({ type: "text", value: value.slice(at) });
  }
  return nodes;
}

/** The URL is the token, path-relative; `PathLink` decodes it back. */
export function pathLinkUrl(raw: string): string {
  // An absolute path stays root-relative as written (`./` in front would make it `.//Users/…`),
  // and carries a mark, because harden spells a workspace path `/models/x` too: `PathLink` links
  // a marked one only inside the scope's own root.
  if (!raw.startsWith("/")) {
    return `./${raw}`;
  }
  const hash = raw.indexOf("#");
  return hash < 0 ? `${raw}${ABSOLUTE_MARK}` : `${raw.slice(0, hash)}${ABSOLUTE_MARK}${raw.slice(hash)}`;
}

function linkFor(raw: string, children: MdNode[]): MdNode {
  return { type: "link", url: pathLinkUrl(raw), children };
}
