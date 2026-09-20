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

export function promptDeliveryMessage(result) {
  if (result.status === "added") return "Added to prompt";
  if (result.status === "copied") return "Copied for prompt";
  if (result.status === "cancelled") return "";
  return result.message || (result.status === "deferred" ? "Choose a prompt destination" : "Could not deliver prompt context");
}
