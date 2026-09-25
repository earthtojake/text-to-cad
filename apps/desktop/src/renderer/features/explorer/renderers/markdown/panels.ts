import { Code2, Eye } from "lucide-react";
import type { FilePanel } from "@hardcore/ui/navigation";

/**
 * The markdown source view's panel id. A tab persists it as its open panel
 * (`FileTabSchema.panel`), so it is a plain string.
 */
export const SOURCE_PANEL = "source";

/**
 * Markdown's one panel: the same bytes read as a document or as source. It is
 * a `body` panel, so it replaces the content rather than sitting in the panel
 * column, and it is still exclusive with the file tree. The label is what
 * pressing it does.
 */
export function markdownPanels(open: string): FilePanel[] {
  return [
    {
      id: SOURCE_PANEL,
      label: open === SOURCE_PANEL ? "View preview" : "View source",
      icon: open === SOURCE_PANEL ? Eye : Code2,
      content: "body",
    },
  ];
}
