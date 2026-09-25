import { defineFileRenderer } from "@hardcore/ui/file-viewer";
import { markdownPanels } from "./panels";

const MARKDOWN_EXTENSIONS = new Set(["md", "markdown", "mdx"]);

export const markdownRenderer = defineFileRenderer<null>({
  id: "markdown",
  priority: 100,
  matches: (file) => MARKDOWN_EXTENSIONS.has(file.extension.toLowerCase()),
  panels: ({ open }) => markdownPanels(open),
  async prepare({ file, source, signal }) {
    if (!source.readText) throw new Error(`This file source cannot read text files: ${file.path}`);
    const text = await source.readText(file.path, { signal });
    return { data: null, text };
  },
  load: () => import("./MarkdownRenderer"),
});

export type { MarkdownRendererData } from "./MarkdownRenderer";
export { capturePristine, documentToMarkdown, markdownToDocument } from "./document";
export { markdownExtensions } from "./schema";
