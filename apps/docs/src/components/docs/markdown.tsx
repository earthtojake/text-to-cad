import type { Element, Root as HastRoot, RootContent as HastContent } from "hast";
import { toJsxRuntime } from "hast-util-to-jsx-runtime";
import { LinkIcon } from "lucide-react";
import type { Blockquote, Root, RootContent } from "mdast";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";
import remarkRehype from "remark-rehype";
import { unified } from "unified";
import { CodeBlock } from "@/components/docs/code-block";
import { resolveLink, type LoadedDoc } from "@/lib/docs/source";
import { siteConfig } from "@/lib/site";

/**
 * A page's Markdown as the site sets it: GitHub-flavoured Markdown, never MDX (a repository file
 * says `<state>` and `{...}` as text). Every link is resolved first (`resolveLink`, which fails the
 * build on one that leads nowhere), a GitHub alert (`> [!NOTE]`) becomes a callout, fenced code is
 * highlighted, and each heading links to itself.
 */

const toHast = unified().use(remarkRehype);

const CALLOUTS: Record<string, string> = {
  NOTE: "Note",
  TIP: "Tip",
  IMPORTANT: "Important",
  WARNING: "Warning",
  CAUTION: "Caution",
};

// `> [!NOTE]` on a blockquote's first line, as GitHub reads it.
function callout(node: Blockquote) {
  const paragraph = node.children[0];
  const text = paragraph?.type === "paragraph" ? paragraph.children[0] : undefined;
  if (text?.type !== "text") return;
  const marker = /^\[!([A-Z]+)\]\s*/.exec(text.value);
  if (!marker || !CALLOUTS[marker[1]]) return;
  text.value = text.value.slice(marker[0].length);
  node.data = {
    hName: "aside",
    hProperties: { className: ["docs-callout"], "data-callout": marker[1].toLowerCase(), "data-label": CALLOUTS[marker[1]] },
  };
}

function prepare(doc: LoadedDoc, node: Root | RootContent) {
  if (node.type === "link") {
    const resolved = resolveLink(doc, node.url);
    node.url = resolved.href;
    if (resolved.external) node.data = { hProperties: { target: "_blank", rel: ["noreferrer"] } };
  } else if (node.type === "image" && !/^https?:/.test(node.url)) {
    // A picture beside a repository file: its raw file on GitHub.
    const github = resolveLink(doc, node.url).href;
    node.url = github.replace(`${siteConfig.repository}/blob/`, `${siteConfig.repository.replace("github.com", "raw.githubusercontent.com")}/`);
  } else if (node.type === "blockquote") {
    callout(node);
  }
  if ("children" in node) for (const child of node.children) prepare(doc, child);
}

const textOf = (node: HastContent): string =>
  node.type === "text" ? node.value : "children" in node ? node.children.map(textOf).join("") : "";

// Fenced code leaves the tree as one element the highlighter takes: its language and its text. A
// fence marked `nocopy` (```python nocopy: a generated reference's signature or usage, read rather
// than run) has no Copy.
function liftCode(node: HastRoot | Element) {
  node.children = node.children.map((child) => {
    if (child.type !== "element") return child;
    const code = child.tagName === "pre" ? child.children.find((inner) => inner.type === "element" && inner.tagName === "code") : undefined;
    if (code?.type === "element") {
      const classes = (code.properties.className as string[] | undefined) ?? [];
      const language = classes.find((name) => name.startsWith("language-"))?.slice("language-".length) ?? "";
      const meta = (code.data as { meta?: string } | undefined)?.meta ?? "";
      const copy = !/(^|\s)nocopy(\s|$)/.test(meta);
      return { type: "element", tagName: "docs-code", properties: { language, code: textOf(code).replace(/\n$/, ""), copy }, children: [] };
    }
    liftCode(child);
    return child;
  }) as HastRoot["children"];
}

// A generated reference page's heading carries its kind (`function`, `class`, ...): a badge after it.
type HeadingProps = { id?: string; children?: ReactNode; "data-kind"?: string };

function Heading({ level, id, kind, children }: { level: 2 | 3 | 4 | 5 | 6; id?: string; kind?: string; children?: ReactNode }) {
  const Tag = `h${level}` as const;
  return (
    <Tag id={id} className="group/heading">
      {children}
      {kind ? <span className="docs-kind">{kind}</span> : null}
      {id ? (
        <a href={`#${id}`} className="docs-anchor" aria-label="Link to this section">
          <LinkIcon aria-hidden="true" />
        </a>
      ) : null}
    </Tag>
  );
}

function Anchor({ href = "", children, ...props }: ComponentProps<"a">) {
  if (href.startsWith("/")) return <Link href={href}>{children}</Link>;
  return (
    <a href={href} {...props}>
      {children}
    </a>
  );
}

export function Markdown({ doc }: { doc: LoadedDoc }) {
  const tree = structuredClone(doc.tree);
  prepare(doc, tree);
  const hast = toHast.runSync(tree) as HastRoot;
  liftCode(hast);
  return (
    <div className={doc.page.source.kind === "generated" ? "docs-prose docs-reference" : "docs-prose"}>
      {toJsxRuntime(hast, {
        Fragment,
        jsx,
        jsxs,
        components: {
          a: Anchor,
          // A page's own title is its h1; a stray one in the text sits a level down.
          h1: ({ id, children, "data-kind": kind }: HeadingProps) => <Heading level={2} id={id} kind={kind}>{children}</Heading>,
          h2: ({ id, children, "data-kind": kind }: HeadingProps) => <Heading level={2} id={id} kind={kind}>{children}</Heading>,
          h3: ({ id, children, "data-kind": kind }: HeadingProps) => <Heading level={3} id={id} kind={kind}>{children}</Heading>,
          h4: ({ id, children, "data-kind": kind }: HeadingProps) => <Heading level={4} id={id} kind={kind}>{children}</Heading>,
          h5: ({ id, children, "data-kind": kind }: HeadingProps) => <Heading level={5} id={id} kind={kind}>{children}</Heading>,
          h6: ({ id, children, "data-kind": kind }: HeadingProps) => <Heading level={6} id={id} kind={kind}>{children}</Heading>,
          table: ({ children }: HeadingProps) => (
            <div className="docs-table">
              <table>{children}</table>
            </div>
          ),
          "docs-code": CodeBlock,
        } as never,
      })}
    </div>
  );
}
