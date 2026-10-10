import { createPromptContext, referencePart } from "@text-to-cad/core/prompt";

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

/**
 * Hand a prompt context to the host. Resolves with the host's result, a refusal or a throw read as
 * a failed one, so a caller has one thing to show (`promptDeliveryError`).
 */
export function deliverPromptContext(host, context) {
  let pending;
  try { pending = host.promptContext.deliver(context); }
  catch (error) { pending = Promise.reject(error); }
  return Promise.resolve(pending).catch(error => ({ status: "failed", message: error instanceof Error ? error.message : String(error) }));
}
