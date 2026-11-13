/**
 * Reads the documentation's pages: each page's Markdown from its file (`nav.ts`), its title, its
 * headings, and every link in it resolved to where it leads on the site or on GitHub.
 *
 * A link that leads nowhere is an error, thrown as the page is built, so `next build` (the docs
 * check) is the documentation's link check: a page of the map that has no file, a `/docs` path that
 * is no page, an anchor that is no heading of its page, and a repository path that does not exist.
 *
 * Server only: it reads files, at build time. Nothing here runs in the browser.
 */
import fs from "node:fs";
import path from "node:path";
import GithubSlugger from "github-slugger";
import type { Root, RootContent } from "mdast";
import { toString } from "mdast-util-to-string";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import { unified } from "unified";
import { siteConfig } from "@/lib/site";
import { docHref, docPages, docSections, findPage, type DocPage } from "./nav";

// The app builds from its own folder (`apps/docs`), in a checkout of the whole repository.
// Every read happens as the site builds (each route is static), so nothing here is traced into a
// server bundle: the paths below are marked for the bundler to leave alone.
const REPO_ROOT = path.resolve(/*turbopackIgnore: true*/ process.cwd(), "../..");
const inRepo = (repoPath: string) => path.join(/*turbopackIgnore: true*/ REPO_ROOT, repoPath);

const parser = unified().use(remarkParse).use(remarkGfm);

export type DocHeading = { depth: number; id: string; text: string };

export type LoadedDoc = {
  page: DocPage;
  href: string;
  title: string;
  description: string;
  /** The page's file, by its path from the repository's root. */
  sourcePath: string;
  /** The page's Markdown, without its front matter and its title. */
  body: string;
  tree: Root;
  /** Every heading of the page. */
  headings: DocHeading[];
};

export class DocsError extends Error {}

function frontMatter(text: string): { data: Record<string, string>; body: string } {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  if (!match) return { data: {}, body: text };
  const data: Record<string, string> = {};
  for (const line of match[1].split(/\r?\n/)) {
    const pair = /^([A-Za-z]+):\s*(.*)$/.exec(line);
    if (pair) data[pair[1]] = pair[2].trim().replace(/^(["'])(.*)\1$/, "$2");
  }
  return { data, body: text.slice(match[0].length) };
}

function summaryOf(tree: Root) {
  const paragraph = tree.children.find((node) => node.type === "paragraph");
  const text = paragraph ? toString(paragraph).replace(/\s+/g, " ").trim() : "";
  if (text.length <= 160) return text;
  return `${text.slice(0, 157).replace(/\s+\S*$/, "")}...`;
}

const loaded = new Map<string, LoadedDoc>();

/** A page of the map, read and parsed (once: a build reads each file a single time). */
export function loadDoc(slug: string): LoadedDoc {
  const cached = loaded.get(slug);
  if (cached) return cached;
  const page = findPage(slug);
  if (!page) throw new DocsError(`/docs/${slug} is no page of the documentation (src/lib/docs/nav.ts)`);

  const sourcePath =
    page.source.kind === "repo" ? page.source.file : path.posix.join("apps/docs/content", page.source.file);
  const file = inRepo(sourcePath);
  if (!fs.existsSync(file)) throw new DocsError(`${docHref(slug)}: its file is missing, ${sourcePath}`);
  const { data, body: withTitle } = frontMatter(fs.readFileSync(file, "utf8"));

  // A repository file says its title as its first heading; a page of the site's, in its front matter.
  const tree = parser.parse(withTitle) as Root;
  let title = data.title ?? "";
  let body = withTitle;
  const first = tree.children[0];
  if (first?.type === "heading" && first.depth === 1) {
    title ||= toString(first);
    tree.children.shift();
    body = withTitle.slice(first.position?.end.offset ?? 0).replace(/^\s+/, "");
  }
  if (!title) throw new DocsError(`${sourcePath}: no title (a front matter \`title\`, or a first \`#\` heading)`);

  // Headings take the ids GitHub gives them, so an anchor written for the file on GitHub works here.
  const slugger = new GithubSlugger();
  const headings: DocHeading[] = [];
  for (const node of tree.children) {
    if (node.type !== "heading") continue;
    const text = toString(node);
    const id = slugger.slug(text);
    node.data = { ...node.data, hProperties: { id } };
    headings.push({ depth: node.depth, id, text });
  }

  const doc: LoadedDoc = {
    page,
    href: docHref(slug),
    title,
    description: data.description || summaryOf(tree),
    sourcePath,
    body,
    tree,
    headings,
  };
  loaded.set(slug, doc);
  return doc;
}

export type ResolvedLink = { href: string; external: boolean };

const repoPages = new Map(
  docPages.flatMap((page) => (page.source.kind === "repo" ? [[page.source.file, page.slug] as const] : [])),
);
// The site's own pages outside /docs that a page may link.
const SITE_PATHS = new Set(["/", "/icon", "/privacy-policy", "/terms-of-service", "/llms.txt", "/install.sh", "/install.ps1"]);

function splitAnchor(target: string) {
  const at = target.indexOf("#");
  return at < 0 ? { path: target, anchor: "" } : { path: target.slice(0, at), anchor: target.slice(at + 1) };
}

function onGitHub(repoPath: string, anchor: string) {
  const kind = fs.statSync(inRepo(repoPath)).isDirectory() ? "tree" : "blob";
  return `${siteConfig.repository}/${kind}/main/${repoPath}${anchor ? `#${anchor}` : ""}`;
}

function toPage(from: LoadedDoc, slug: string, anchor: string, written: string): ResolvedLink {
  const target = slug === from.page.slug ? from : loadDoc(slug);
  if (anchor && !target.headings.some((heading) => heading.id === anchor)) {
    throw new DocsError(`${from.sourcePath}: the link ${written} names an anchor ${target.href} does not have, #${anchor}`);
  }
  return { href: `${target.href}${anchor ? `#${anchor}` : ""}`, external: false };
}

function toRepo(from: LoadedDoc, repoPath: string, anchor: string, written: string): ResolvedLink {
  const clean = repoPath.replace(/\/$/, "");
  if (clean.startsWith("..") || path.posix.isAbsolute(clean)) {
    throw new DocsError(`${from.sourcePath}: the link ${written} leaves the repository`);
  }
  // A file of the repository that is itself a page links to the page.
  const slug = repoPages.get(clean);
  if (slug !== undefined) return toPage(from, slug, anchor, written);
  if (!fs.existsSync(inRepo(clean))) {
    throw new DocsError(`${from.sourcePath}: the link ${written} names a path the repository does not have, ${clean}`);
  }
  return { href: onGitHub(clean, anchor), external: true };
}

/**
 * Where a link written in a page leads. A page of the site's writes `/docs/...` for another page,
 * `repo:<path>` for a file of the repository, and a full URL for anything else; a repository file
 * writes relative paths, as GitHub reads them.
 */
export function resolveLink(from: LoadedDoc, written: string): ResolvedLink {
  if (/^(https?:|mailto:)/.test(written)) return { href: written, external: true };
  const { path: target, anchor } = splitAnchor(written);
  if (!target) return toPage(from, from.page.slug, anchor, written);
  if (target.startsWith("repo:")) return toRepo(from, target.slice("repo:".length), anchor, written);
  if (target === "/docs" || target.startsWith("/docs/")) {
    const slug = target.slice("/docs".length).replace(/^\/|\/$/g, "");
    if (!findPage(slug)) throw new DocsError(`${from.sourcePath}: the link ${written} names a page that does not exist`);
    return toPage(from, slug, anchor, written);
  }
  if (target.startsWith("/")) {
    if (!SITE_PATHS.has(target)) throw new DocsError(`${from.sourcePath}: the link ${written} names a path the site does not have`);
    return { href: written, external: false };
  }
  if (from.page.source.kind === "content") {
    throw new DocsError(
      `${from.sourcePath}: the link ${written} is relative; write /docs/<page>, repo:<path from the repository's root> or a full URL`,
    );
  }
  const repoPath = path.posix.normalize(path.posix.join(path.posix.dirname(from.sourcePath), decodeURI(target)));
  return toRepo(from, repoPath, anchor, written);
}

/** The sidebar: each section's pages, with the name each shows by. */
export function navigation() {
  return docSections.map((section) => ({
    title: section.title,
    pages: section.pages.map((page) => ({
      href: docHref(page.slug),
      label: page.label ?? loadDoc(page.slug).title,
    })),
  }));
}

/** The page before and the page after, in the sidebar's order. */
export function neighbours(slug: string) {
  const at = docPages.findIndex((page) => page.slug === slug);
  const link = (page: DocPage | undefined) =>
    page ? { href: docHref(page.slug), title: loadDoc(page.slug).title } : null;
  return { previous: link(docPages[at - 1]), next: link(docPages[at + 1]) };
}

export type SearchRecord = { href: string; page: string; section: string; heading: string; text: string };

const SEARCH_TEXT_LIMIT = 1600;

// A block's text with its parts apart: a list's items and a table's cells, each a word on.
const BLOCKS = new Set(["list", "listItem", "table", "tableRow", "blockquote"]);
function blockText(node: RootContent): string {
  return BLOCKS.has(node.type) && "children" in node
    ? (node.children as RootContent[]).map(blockText).join(" ")
    : toString(node);
}

/** What the search reads: each page cut at its headings, a record per part. */
export function searchRecords(): SearchRecord[] {
  return docSections.flatMap((section) =>
    section.pages.flatMap((page) => {
      const doc = loadDoc(page.slug);
      const records: SearchRecord[] = [];
      let current: SearchRecord = { href: doc.href, page: doc.title, section: section.title, heading: "", text: doc.description };
      const close = () => {
        current.text = current.text.replace(/\s+/g, " ").trim().slice(0, SEARCH_TEXT_LIMIT);
        records.push(current);
      };
      for (const node of doc.tree.children) {
        if (node.type === "heading" && node.depth <= 3) {
          close();
          const id = (node.data?.hProperties as { id?: string } | undefined)?.id;
          current = { href: `${doc.href}#${id}`, page: doc.title, section: section.title, heading: toString(node), text: "" };
        } else {
          current.text += ` ${blockText(node)}`;
        }
      }
      close();
      return records;
    }),
  );
}

// A page's Markdown with every link made absolute, for /docs/<page>.md: links are rewritten where
// they are written, outside fenced code.
function withAbsoluteLinks(doc: LoadedDoc) {
  const absolute = (href: string) => {
    const resolved = resolveLink(doc, href);
    return resolved.external || resolved.href.startsWith("#") ? resolved.href : `${siteConfig.origin}${resolved.href}`;
  };
  return doc.body
    .split(/(^ {0,3}(?:```|~~~)[\s\S]*?^ {0,3}(?:```|~~~)[^\n]*$)/m)
    .map((part, index) =>
      index % 2
        ? part
        : part.replace(/(?<!!)\[((?:[^\]\\]|\\.)*)\]\(([^)\s]+)\)/g, (whole, text: string, href: string) => {
            try {
              return `[${text}](${absolute(href)})`;
            } catch {
              // Not a link after all (inline code that looks like one): left as written.
              return whole;
            }
          }),
    )
    .join("");
}

/** A page as Markdown, for an agent: its title, what it is, then its text with absolute links. */
export function docMarkdown(slug: string, generated = "") {
  const doc = loadDoc(slug);
  return [`# ${doc.title}`, "", `> ${doc.description}`, "", withAbsoluteLinks(doc).trimEnd(), generated ? `\n${generated.trimEnd()}` : "", ""]
    .join("\n")
    .replace(/\n{3,}/g, "\n\n");
}
