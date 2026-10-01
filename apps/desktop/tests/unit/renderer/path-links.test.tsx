import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { findPathTokens, looksLikePath, pathToken } from "@renderer/features/session/links/grammar";
import { PartsList } from "@renderer/features/session/parts/PartsList";
import { PathLink, TranscriptScopeContext, pathTarget } from "@renderer/features/session/links/PathLink";
import { TranscriptImage } from "@renderer/features/session/links/TranscriptImage";
import { remarkPathLinks } from "@renderer/features/session/links/remarkPathLinks";
import { useExplorer } from "@renderer/state/explorer";
import { scopeKey, usePathLinks } from "@renderer/state/path-links";

/**
 * Workspace-relative paths in an agent's prose become links (plan §8), and
 * only when they exist. Three layers, tested apart: the grammar that finds
 * a path-shaped token, the remark plugin that wraps it, the store that asks
 * main whether it is there, and the component that turns the answer into a
 * button or leaves the words alone.
 */

describe("the path grammar", () => {
  it("recognises relative paths and file names, not versions, URLs or absolute paths", () => {
    for (const yes of ["models/bracket.step", "README.md", "src/", "src/main", "apps/desktop/AGENTS.md", "Makefile.in", "a.b/c", "/Users/me/p/a.step", "/etc/hosts", "v1..v2.txt", "..keep/a.txt"]) {
      expect(looksLikePath(yes), yes).toBe(true);
    }
    for (const no of ["0.5.0", "3.14", "https://x.y/z", "/clear", "//x/y", "~/x", "C:\\x", "foo:", "../x", "a/../b", "hello", "."]) {
      expect(looksLikePath(no), no).toBe(false);
    }
  });

  it("finds an absolute path in prose and keeps its leading slash", () => {
    expect(findPathTokens("Wrote /Users/me/proj/models/a.step#o1, done.").map((token) => [token.raw, token.path, token.selector])).toEqual([
      ["/Users/me/proj/models/a.step#o1", "/Users/me/proj/models/a.step", "o1"],
    ]);
  });

  it("finds tokens in prose, shedding the sentence's punctuation", () => {
    const text = "Built STEP/bracket.step (see README.md). Check models/x.step#o1.2, then `src/`.";
    expect(findPathTokens(text).map((token) => [token.raw, token.path, token.selector])).toEqual([
      ["STEP/bracket.step", "STEP/bracket.step", ""],
      ["README.md", "README.md", ""],
      ["models/x.step#o1.2", "models/x.step", "o1.2"],
      ["src/", "src", ""],
    ]);
  });

  it("keeps a selector only on a file that can carry one, and reads every selector form", () => {
    expect(findPathTokens("bracket.step#label.f45.")[0]).toMatchObject({ raw: "bracket.step#label.f45", selector: "label.f45" });
    expect(findPathTokens("assy.step#o1,o2")[0]).toMatchObject({ selector: "o1" });
    expect(findPathTokens("part.step.py#o1")[0]).toMatchObject({ path: "part.step.py", selector: "o1" });
    expect(findPathTokens("notes.md#o1")[0]).toMatchObject({ raw: "notes.md", selector: "" });
    // `#not` is a label selector; `#9x` is nothing, and the file stands alone.
    expect(findPathTokens("bracket.step#not a selector")[0]).toMatchObject({ raw: "bracket.step#not", selector: "not" });
    expect(findPathTokens("bracket.step#9x")[0]).toMatchObject({ raw: "bracket.step", selector: "" });
    expect(findPathTokens("run ./build.sh now")[0]).toMatchObject({ raw: "./build.sh", path: "build.sh" });
  });

  it("takes a whole code span as one token, or none", () => {
    expect(pathToken("models/bracket.step#o1")).toMatchObject({ path: "models/bracket.step", selector: "o1" });
    expect(pathToken("cadgen step inspect")).toBeNull();
    expect(pathToken("npm")).toBeNull();
  });
});

describe("remarkPathLinks", () => {
  const run = (tree: unknown) => {
    remarkPathLinks()(tree as never);
    return tree;
  };

  it("splits a text node around its paths and wraps a code span that is a path", () => {
    const tree = run({
      type: "root",
      children: [
        {
          type: "paragraph",
          children: [
            { type: "text", value: "Open models/x.step#o1 and " },
            { type: "inlineCode", value: "README.md" },
            { type: "text", value: ", not " },
            { type: "inlineCode", value: "npm test" },
            { type: "link", url: "https://example.com", children: [{ type: "text", value: "docs/x.md" }] },
          ],
        },
      ],
    }) as { children: Array<{ children: Array<{ type: string; url?: string; value?: string; children?: unknown[] }> }> };
    const nodes = tree.children[0]!.children;
    expect(nodes.map((node) => node.type)).toEqual(["text", "link", "text", "link", "text", "inlineCode", "link"]);
    expect(nodes[1]).toMatchObject({ url: "./models/x.step#o1", children: [{ type: "text", value: "models/x.step#o1" }] });
    expect(nodes[3]).toMatchObject({ url: "./README.md", children: [{ type: "inlineCode", value: "README.md" }] });
    // A link the agent wrote stays as it was, path-shaped text inside and all.
    expect(nodes[6]).toMatchObject({ url: "https://example.com", children: [{ type: "text", value: "docs/x.md" }] });
  });
});

describe("pathTarget", () => {
  it("reads a marked absolute path only inside the root: outside it, or with no root known, it is words", () => {
    expect(pathTarget("/Users/me/p/models/a.step?abs#o1", "/Users/me/p")).toEqual({ path: "models/a.step", selector: "o1" });
    expect(pathTarget("/etc/hosts?abs", "/Users/me/p")).toBeNull();
    expect(pathTarget("/Users/me/pp/a.step?abs", "/Users/me/p")).toBeNull();
    expect(pathTarget("/etc/hosts?abs")).toBeNull();
  });

  it("reads an absolute path inside the root against it, and one outside as a workspace path that is not there", () => {
    expect(pathTarget("/Users/me/p/models/a.step#o1", "/Users/me/p")).toEqual({ path: "models/a.step", selector: "o1" });
    expect(pathTarget("/Users/me/p/", "/Users/me/p/")).toBeNull();
    expect(pathTarget("/Users/me/other/a.step", "/Users/me/p")).toEqual({ path: "Users/me/other/a.step", selector: "" });
    expect(pathTarget("/Users/me/pp/a.step", "/Users/me/p")).toEqual({ path: "Users/me/pp/a.step", selector: "" });
  });

  it("reads the path and selector back from the hrefs the pipeline produces", () => {
    expect(pathTarget("./models/x.step#o1.2")).toEqual({ path: "models/x.step", selector: "o1.2" });
    expect(pathTarget("/models/x.step#label.f45")).toEqual({ path: "models/x.step", selector: "label.f45" });
    expect(pathTarget("/a%20b/c.md")).toEqual({ path: "a b/c.md", selector: "" });
    expect(pathTarget("models/x.step")).toEqual({ path: "models/x.step", selector: "" });
    expect(pathTarget("https://example.com/x.step")).toBeNull();
    expect(pathTarget("mailto:a@b.c")).toBeNull();
    expect(pathTarget("/../etc")).toBeNull();
    expect(pathTarget("../x")).toBeNull();
    expect(pathTarget("docs/..%2Fx")).toBeNull();
    expect(pathTarget("v1..v2.txt")).toMatchObject({ path: "v1..v2.txt" });
    expect(pathTarget("..keep/a.txt")).toMatchObject({ path: "..keep/a.txt" });
  });
});

describe("the path-links store", () => {
  beforeEach(() => {
    usePathLinks.setState({ kinds: {} });
  });

  it("asks once per root per tick and caches the answers", async () => {
    const exists = vi.fn(async ({ paths }: { paths: string[] }) =>
      Object.fromEntries(paths.map((path) => [path, path.endsWith(".md") ? "file" : path === "src" ? "directory" : null])),
    );
    (window.textToCad.explorer as unknown as Record<string, unknown>).exists = exists;
    const scope = { projectId: "p1", root: null };
    usePathLinks.getState().lookup(scope, ["README.md", "src"]);
    usePathLinks.getState().lookup(scope, ["README.md", "nope.txt"]);
    usePathLinks.getState().lookup({ projectId: "p1", root: "/wt/slug" }, ["README.md"]);
    expect(usePathLinks.getState().kinds[scopeKey(scope)]?.["README.md"]).toBe("pending");
    await usePathLinks.getState().flush();
    expect(exists).toHaveBeenCalledTimes(2);
    expect(exists.mock.calls[0]?.[0]).toEqual({ projectId: "p1", paths: ["README.md", "src", "nope.txt"] });
    expect(exists.mock.calls[1]?.[0]).toEqual({ projectId: "p1", root: "/wt/slug", paths: ["README.md"] });
    expect(usePathLinks.getState().kinds[scopeKey(scope)]).toEqual({ "README.md": "file", src: "directory", "nope.txt": null });

    usePathLinks.getState().invalidate(scope, ["nope.txt"]);
    expect(usePathLinks.getState().kinds[scopeKey(scope)]).toEqual({ "README.md": "file", src: "directory" });
  });
});

describe("PathLink", () => {
  const scope = { projectId: "p1", root: null };
  const wrap = (href: string, label = href) =>
    render(
      <TranscriptScopeContext.Provider value={scope}>
        <PathLink href={href}>{label}</PathLink>
      </TranscriptScopeContext.Provider>,
    );

  beforeEach(() => {
    usePathLinks.setState({ kinds: {} });
    window.localStorage.clear();
    useExplorer.setState({ sessionId: "s1", projectId: "p1", root: null, tabs: [], activeId: null, ready: true, collapsed: true, cadSelection: null, reveal: null });
  });

  it("is the words it was until the path is known to exist, then a link that opens the file", async () => {
    const user = userEvent.setup();
    (window.textToCad.explorer as unknown as Record<string, unknown>).exists = vi.fn(async () => ({ "models/x.step": "file" }));
    wrap("./models/x.step#o1.2", "models/x.step#o1.2");
    expect(screen.queryByRole("button")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: /models\/x\.step#o1\.2/ })).toBeInTheDocument());
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("data-path-selector", "o1.2");
    await user.click(button);
    const { tabs, cadSelection } = useExplorer.getState();
    expect(tabs).toHaveLength(1);
    expect(tabs[0]).toMatchObject({ kind: "file", path: "models/x.step", root: null });
    expect(cadSelection).toMatchObject({ tabId: tabs[0]!.id, selector: "o1.2" });
  });

  it("reveals a directory in the tree", async () => {
    const user = userEvent.setup();
    (window.textToCad.explorer as unknown as Record<string, unknown>).exists = vi.fn(async () => ({ src: "directory" }));
    wrap("./src/", "src/");
    await waitFor(() => expect(screen.getByRole("button")).toBeInTheDocument());
    await user.click(screen.getByRole("button"));
    expect(useExplorer.getState().reveal).toEqual({ path: "src", directory: true, root: null });
    expect(useExplorer.getState().tabs[0]).toMatchObject({ kind: "file", path: null });
  });

  it("an absolute path inside the project renders a link to the file; one outside stays words", async () => {
    const exists = vi.fn(async ({ paths }: { paths: string[] }) => Object.fromEntries(paths.map((path) => [path, path === "models/a.step" ? "file" : null])));
    (window.textToCad.explorer as unknown as Record<string, unknown>).exists = exists;
    const rooted = { projectId: "p1", root: null, rootPath: "/Users/me/p" };
    render(
      <TranscriptScopeContext.Provider value={rooted}>
        <PathLink href="/Users/me/p/models/a.step">/Users/me/p/models/a.step</PathLink>
        <PathLink href="/Users/me/elsewhere/b.step">/Users/me/elsewhere/b.step</PathLink>
      </TranscriptScopeContext.Provider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: /\/Users\/me\/p\/models\/a\.step/ })).toHaveAttribute("data-path-link", "models/a.step"));
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("an exists error is not pinned: the next hover asks again and the answer becomes a link", async () => {
    const user = userEvent.setup();
    const exists = vi
      .fn<(request: { paths: string[] }) => Promise<Record<string, string | null>>>()
      .mockRejectedValueOnce(new Error("ipc down"))
      .mockResolvedValue({ "models/x.step": "file" });
    (window.textToCad.explorer as unknown as Record<string, unknown>).exists = exists;
    wrap("./models/x.step", "models/x.step");
    await waitFor(() => expect(screen.getByText("models/x.step")).toHaveAttribute("data-path-retry"));
    expect(screen.queryByRole("button")).toBeNull();
    expect(exists).toHaveBeenCalledTimes(1);
    await user.hover(screen.getByText("models/x.step"));
    await waitFor(() => expect(screen.getByRole("button", { name: /models\/x\.step/ })).toBeInTheDocument());
    expect(exists).toHaveBeenCalledTimes(2);
  });

  it("leaves a missing path as text and a URL as an outside link", async () => {
    (window.textToCad.explorer as unknown as Record<string, unknown>).exists = vi.fn(async () => ({ "gone.md": null }));
    wrap("./gone.md", "gone.md");
    await usePathLinks.getState().flush();
    await waitFor(() => expect(usePathLinks.getState().kinds[scopeKey(scope)]?.["gone.md"]).toBeNull());
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("gone.md")).toHaveAttribute("data-path-text", "gone.md");

    wrap("https://example.com/docs", "the docs");
    expect(screen.getByRole("link", { name: "the docs" })).toHaveAttribute("href", "https://example.com/docs");
  });

  /**
   * An outside link opens in one click, and its label is the agent's words —
   * `[docs.python.org](https://somewhere.else/…)` reads as one place and goes
   * to another. The hint says where it really goes (the kit's, not a native
   * `title`).
   */
  it("says where an outside link really goes on hover", async () => {
    const user = userEvent.setup();
    wrap("https://somewhere.example/collect?d=1", "docs.python.org");
    const link = screen.getByRole("link", { name: "docs.python.org" });
    expect(link).not.toHaveAttribute("title");
    await user.hover(link);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("https://somewhere.example/collect?d=1");
  });

  it("breaks a long URL inside the hint rather than running out of its box", async () => {
    const user = userEvent.setup();
    const long = "https://example.org/very/long/path/that/goes/on/and/on/and/on/and/on/and/on/and/on/and/on?query=1&other=2";
    wrap(long, long);
    await user.hover(screen.getByRole("link"));
    await screen.findByRole("tooltip");
    const hint = document.querySelector("[data-slot=tooltip-content] [data-link-hint]");
    expect(hint).toHaveClass("break-all");
  });
});

describe("an absolute path in an agent's prose, through the markdown pipeline", () => {
  it("becomes a link when it lies inside the project", async () => {
    usePathLinks.setState({ kinds: {} });
    (window.textToCad.explorer as unknown as Record<string, unknown>).exists = vi.fn(async ({ paths }: { paths: string[] }) =>
      Object.fromEntries(paths.map((path) => [path, path === "models/a.step" ? "file" : null])),
    );
    render(
      <TranscriptScopeContext.Provider value={{ projectId: "p1", root: null, rootPath: "/Users/me/p" }}>
        <PartsList open={false} parts={[{ type: "text", text: "Wrote `/Users/me/p/models/a.step` and /usr/bin/env." }]} prefix="t" sessionId="s1" />
      </TranscriptScopeContext.Provider>,
    );
    const link = await screen.findByRole("button", { name: /models\/a\.step/ });
    expect(link).toHaveAttribute("data-path-link", "models/a.step");
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });
});

describe("an absolute path outside the root, and a root the grammar cannot hold", () => {
  const exists = (known: Record<string, "file">) =>
    vi.fn(async ({ paths }: { paths: string[] }) => Object.fromEntries(paths.map((path) => [path, known[path] ?? null])));
  const prose = (text: string, rootPath: string) =>
    render(
      <TranscriptScopeContext.Provider value={{ projectId: "p1", root: null, rootPath }}>
        <PartsList open={false} parts={[{ type: "text", text }]} prefix="t" sessionId="s1" />
      </TranscriptScopeContext.Provider>,
    );

  beforeEach(() => usePathLinks.setState({ kinds: {} }));

  it("stays words in prose even when the same path exists under the root", async () => {
    // `<root>/etc/hosts` exists; `/etc/hosts` is somewhere else entirely.
    (window.textToCad.explorer as unknown as Record<string, unknown>).exists = exists({ "etc/hosts": "file", "models/a.step": "file" });
    prose("See /etc/hosts and /Users/me/p/models/a.step.", "/Users/me/p");
    const link = await screen.findByRole("button", { name: /models\/a\.step/ });
    expect(link).toHaveAttribute("data-path-link", "models/a.step");
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /hosts/ })).toBeNull();
  });

  it("links an absolute path under a root with a space in it", async () => {
    (window.textToCad.explorer as unknown as Record<string, unknown>).exists = exists({ "models/a.step": "file", "b.md": "file" });
    prose("Wrote /Users/me/My Project/models/a.step#o1 and `/Users/me/My Project/b.md`.", "/Users/me/My Project");
    const link = await screen.findByRole("button", { name: /models\/a\.step/ });
    expect(link).toHaveAttribute("data-path-link", "models/a.step");
    expect(link).toHaveAttribute("data-path-selector", "o1");
    expect(await screen.findByRole("button", { name: /b\.md/ })).toHaveAttribute("data-path-link", "b.md");
  });

  it("reads an image at an absolute path under the root through the project", async () => {
    const readBinary = vi.mocked(window.textToCad.explorer.readBinary);
    readBinary.mockResolvedValue({ path: "render.png", mime: "image/png", size: 4, dataUrl: "data:image/png;base64,AAAA" });
    render(
      <TranscriptScopeContext.Provider value={{ projectId: "p1", root: null, rootPath: "/Users/me/p" }}>
        <TranscriptImage alt="r" src="/Users/me/p/render.png" />
      </TranscriptScopeContext.Provider>,
    );
    expect(await screen.findByAltText("r")).toHaveAttribute("src", "data:image/png;base64,AAAA");
    expect(readBinary).toHaveBeenCalledWith({ projectId: "p1", path: "render.png" });
  });
});
