import { createPromptContext, referencePart } from "@hardcore/core/prompt";

/**
 * One prompt context for a view: the file as a whole-resource reference (or the
 * references the renderer resolved itself), and the PNG that depicts them. Built
 * once, before asynchronous image encoding or host routing.
 */
export function createViewPromptContext({ resource, references = [], capture, operationId }) {
  const parts = references.map((reference, index) => referencePart(reference, `reference-${index}`));
  if (capture) {
    if (!parts.length) parts.push(referencePart({ resource: { ...resource }, target: { kind: "whole-resource" } }, "source"));
    const name = `${String(resource.path || "view").split("/").pop().replace(/\.[^.]+$/, "")}-view.png`;
    parts.push({ id: "capture", kind: "attachment", name, mimeType: "image/png", content: capture, about: parts.map(part => part.id) });
  }
  return createPromptContext(parts, operationId);
}

/** Only failed or incomplete deliveries need an inline error; success is silent. */
export function promptDeliveryError(result) {
  if (result.status !== "failed" && result.status !== "partial") return null;
  return result.message || "Could not deliver prompt context";
}
