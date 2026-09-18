import { formatPromptReference, validatePromptContext } from "@hardcore/core/prompt";
import type { PromptContext, PromptContextPort, PromptDeliveryResult, PromptDestinationState } from "@hardcore/core/prompt";

import { bindDraftDestination, DraftDestinationGone, draftDestinationIsCurrent, validateDraftDestination } from "@renderer/state/cad-draft";
import type { DraftDestination } from "@renderer/state/cad-draft";
import { useComposer } from "@renderer/state/composer";
import type { DraftPart } from "@renderer/state/composer";
import { useSessions } from "@renderer/state/sessions";

const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const message = (error: unknown) => error instanceof Error ? error.message : String(error);
const capabilities = Object.freeze({ attachments: "images-and-text" as const, maxParts: 128, maxAttachmentBytes: MAX_ATTACHMENT_BYTES, maxTotalAttachmentBytes: 40 * 1024 * 1024, mixedTextAndImage: "atomic" as const });
function consumeAttachmentRejections(context: PromptContext) {
  if (!context || !Array.isArray(context.parts)) return;
  for (const part of context.parts) if (part?.kind === "attachment" && part.content) void Promise.resolve(part.content).catch(() => {});
}

async function attachmentFile(part: Extract<PromptContext["parts"][number], { kind: "attachment" }>): Promise<File> {
  const blob = await part.content;
  if (!blob || typeof blob.arrayBuffer !== "function" || blob.type !== part.mimeType || blob.size > MAX_ATTACHMENT_BYTES) {
    throw new Error(`${part.name} must have its declared MIME type and be at most 20 MiB.`);
  }
  const bytes = new Uint8Array(await blob.arrayBuffer());
  if (part.mimeType.startsWith("image/")) {
    const prefix = [...bytes.subarray(0, 12)];
    const valid = part.mimeType === "image/png" ? [137, 80, 78, 71, 13, 10, 26, 10].every((byte, i) => prefix[i] === byte)
      : part.mimeType === "image/jpeg" ? prefix[0] === 255 && prefix[1] === 216 && prefix[2] === 255
      : part.mimeType === "image/gif" ? new TextDecoder().decode(bytes.subarray(0, 6)).match(/^GIF8[79]a$/)
      : part.mimeType === "image/webp" ? new TextDecoder().decode(bytes.subarray(0, 4)) === "RIFF" && new TextDecoder().decode(bytes.subarray(8, 12)) === "WEBP"
      : false;
    if (!valid) throw new Error(`${part.name} is not a supported encoded image.`);
  } else {
    if (bytes.includes(0)) throw new Error(`${part.name} is not a supported text or image attachment.`);
    try { new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
    catch { throw new Error(`${part.name} is not a supported text or image attachment.`); }
  }
  return new File([blob], part.name, { type: part.mimeType });
}

/** Every renderer action addresses the immutable session that owns its tab. */
export function createDesktopPromptContext(projectId: string, root: string | null, workspaceId: string, sessionId: string): PromptContextPort {
  const operations = new Map<string, Promise<PromptDeliveryResult>>();
  const pending = new Set<string>();
  const remember = (operationId: string, operation: Promise<PromptDeliveryResult>) => {
    while (operations.size >= 256) {
      const completed = [...operations.keys()].find(id => !pending.has(id));
      if (!completed) break;
      operations.delete(completed);
    }
    operations.set(operationId, operation);
    pending.add(operationId);
    void operation.then(result => {
      pending.delete(operationId);
      if (result.status === "failed" || result.status === "cancelled") operations.delete(operationId);
    });
    return operation;
  };
  let snapshot: PromptDestinationState = { kind: "composer", available: true, capabilities };
  const getSnapshot = () => {
    const owner = useSessions.getState().sessions.find(session => session.id === sessionId);
    const available = Boolean(owner && !owner.archived && owner.projectId === projectId);
    if (snapshot.available !== available) snapshot = available ? { kind: "composer", available: true, capabilities } : { kind: "composer", available: false, reason: "This tab's session is no longer active.", capabilities };
    return snapshot;
  };
  const materialize = async (context: PromptContext): Promise<DraftPart[]> => {
    const parts: DraftPart[] = [];
    let bytes = 0;
    for (const part of context.parts) {
      if (part.kind === "text") { parts.push({ ...part }); continue; }
      if (part.kind === "attachment") {
        const file = await attachmentFile(part);
        bytes += file.size;
        if (bytes > 40 * 1024 * 1024) throw new Error("Prompt attachments must total at most 40 MiB.");
        parts.push({ id: part.id, kind: "attachment", file, about: part.about });
        continue;
      }
      const resource = part.reference.resource;
      if (resource.kind === "workspace-file" && resource.workspaceId !== workspaceId) throw new Error("This reference belongs to another workspace.");
      parts.push({ id: part.id, kind: "reference", text: formatPromptReference(part.reference), label: part.reference.label, reference: part.reference });
    }
    return parts;
  };
  const accept = async (context: PromptContext, destination: DraftDestination): Promise<PromptDeliveryResult> => {
    const parts = await materialize(context);
    validateDraftDestination(destination);
    const accepted = useComposer.getState().acceptContext(destination.key, context.operationId, parts, { root: destination.workspace, focus: draftDestinationIsCurrent(destination) });
    if (accepted.key !== destination.key) return { status: "failed", message: "This operation already belongs to another session." };
    return { status: "added", partIds: accepted.partIds };
  };
  return {
    getSnapshot,
    subscribe: listener => {
      const unsubscribes = [useSessions.subscribe(listener), useComposer.subscribe(listener)];
      return () => unsubscribes.forEach(unsubscribe => unsubscribe());
    },
    deliver(context) {
      consumeAttachmentRejections(context);
      try { validatePromptContext(context); }
      catch (error) { return Promise.resolve({ status: "failed", message: message(error) }); }
      const receipts = useComposer.getState().acceptedContexts;
      const accepted = Object.hasOwn(receipts, context.operationId) ? receipts[context.operationId] : undefined;
      if (accepted) return Promise.resolve(accepted.key === sessionId
        ? { status: "added", partIds: accepted.partIds }
        : { status: "failed", message: "This operation already belongs to another session." });
      const previous = operations.get(context.operationId);
      if (previous) return previous;
      if (pending.size >= 16) return Promise.resolve({ status: "failed", message: "Wait for pending prompt context before adding more." });
      let operation: Promise<PromptDeliveryResult>;
      try {
        validatePromptContext(context);
        if (context.parts.length > 128) throw new Error("Prompt context has too many parts.");
        if (context.parts.reduce((total, part) => total + (part.kind === "text" ? part.text.length : 0), 0) > 1024 * 1024) throw new Error("Prompt text must be at most 1 MiB.");
        let knownBytes = 0;
        for (const part of context.parts) if (part.kind === "attachment" && "size" in part.content) {
          knownBytes += part.content.size;
          if (part.content.size > MAX_ATTACHMENT_BYTES || knownBytes > 40 * 1024 * 1024) throw new Error("Prompt attachments exceed the draft's size limits.");
        }
        const frozen: PromptContext = { ...context, parts: context.parts.map(part => part.kind === "reference" ? { ...part, reference: structuredClone(part.reference) } : part.kind === "attachment" ? { ...part, about: part.about ? [...part.about] : undefined } : { ...part }) };
        const destination = bindDraftDestination(projectId, root, sessionId);
        operation = accept(frozen, destination).catch(error => ({
          status: error instanceof DraftDestinationGone || (error instanceof Error && error.name === "AbortError") ? "cancelled" : "failed",
          message: message(error),
        }));
      } catch (error) { operation = Promise.resolve({ status: error instanceof DraftDestinationGone ? "cancelled" : "failed", message: message(error) }); }
      return remember(context.operationId, operation);
    },
  };
}
