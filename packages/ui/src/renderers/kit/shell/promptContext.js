import { createPromptContext, referencePart } from "@cad/core/prompt";

const sameResource = (one, other) => one?.kind === other?.kind && (one.kind === "url" ? one.url === other.url : one.path === other.path);

/**
 * A reference as the host's prompts name the document on screen (`subject`, the host's `promptSubject`): one into
 * that document (`shown`, as the view names it) names the host's resource for it, its target kept; any other, and
 * every reference where the host names none, is as it is.
 */
export function subjectReference(reference, shown, subject) {
  return subject?.resource && sameResource(reference.resource, shown) ? { ...reference, resource: { ...subject.resource } } : reference;
}

/**
 * One prompt context for a view: the file as a whole-resource reference (or the
 * references the renderer resolved itself), and the PNG that depicts them, as the host's
 * prompts name the file (`subject`: its resource for it). Built once, before asynchronous
 * image encoding or host routing.
 */
export function createViewPromptContext({ resource, references = [], capture, operationId, subject = null }) {
  const named = references.map((reference, index) => referencePart(subjectReference(reference, resource, subject), `reference-${index}`));
  if (capture && !named.length) {
    named.push(referencePart(subjectReference({ resource: { ...resource }, target: { kind: "whole-resource" } }, resource, subject), "source"));
  }
  const parts = [...named];
  if (capture) {
    const name = `${String(resource.path || "view").split("/").pop().replace(/\.[^.]+$/, "")}-view.png`;
    parts.push({ id: "capture", kind: "attachment", name, mimeType: "image/png", content: capture, about: named.map(part => part.id) });
  }
  return createPromptContext(parts, operationId);
}

/** Only failed or incomplete deliveries need an inline error; success is silent. */
export function promptDeliveryError(result) {
  if (result.status !== "failed" && result.status !== "partial") return null;
  return result.message || "Could not deliver prompt context";
}
