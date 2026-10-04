import { createPromptContext, formatPromptMessage, referencePart, textPart } from "@text-to-cad/core/prompt";

const stem = path => String(path || "").split("/").pop().replace(/\.[^.]+$/, "") || "view";

/** What a sketch is saved and attached as: the view of `bracket.step` with its ink is `bracket-sketch.png`. */
export const sketchName = resource => `${stem(resource.kind === "url" ? new URL(resource.url).pathname : resource.path)}-sketch.png`;

/** The selection a Quick Edit attaches: what is picked in the file, not the file itself, which it always attaches. */
export const quickEditSelection = references => references.filter(reference => reference.target.kind !== "whole-resource");

/**
 * A Quick Edit as one prompt context: what the person wrote, the file on screen (always), the
 * selection in it (`references`, in the prompt grammar), and the view with the sketch drawn over
 * it (`sketch`, a PNG that may still be encoding). Built at the press, from what is live then.
 */
export function createQuickEditContext({ resource, references = [], text, sketch = null }) {
  const parts = [
    textPart(String(text || "").trim(), "text"),
    referencePart({ resource: { ...resource }, target: { kind: "whole-resource" } }, "file"),
    ...quickEditSelection(references).map((reference, index) => referencePart({ ...reference, resource: { ...reference.resource } }, `reference-${index}`)),
  ];
  if (sketch) parts.push({ id: "sketch", kind: "attachment", label: "Sketch", name: sketchName(resource), mimeType: "image/png", content: sketch, about: ["file"] });
  return createPromptContext(parts);
}

/**
 * A Quick Edit as the person copies it: its references by their files' absolute paths, and its
 * sketch by the path it was saved at, since text cannot carry a picture.
 */
export function copiedQuickEdit(context, { sketchPath = null } = {}) {
  return formatPromptMessage(context, { attachmentPath: () => sketchPath });
}
