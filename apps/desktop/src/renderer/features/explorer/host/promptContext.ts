import { formatPromptReference, validatePromptContext } from "@hardcore/core/prompt";
import type { PromptContext, PromptContextPort, PromptDeliveryResult, PromptDestinationState } from "@hardcore/core/prompt";
import { toast } from "sonner";

import { bindDraftDestination, DraftDestinationGone, draftDestinationIsCurrent, validateDraftDestination, WorkspaceMismatch } from "@renderer/state/cad-draft";
import type { DraftDestination } from "@renderer/state/cad-draft";
import { useComposer } from "@renderer/state/composer";
import type { DraftPart } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";

const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;
const message = (error: unknown) => error instanceof Error ? error.message : String(error);
const pendingOffers = new Map<string, { release(): void }>();
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

/** Every renderer and file-menu action converges on this workspace-bound draft port. */
export function createDesktopPromptContext(projectId: string, root: string | null, workspaceId: string): PromptContextPort {
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
    const projects = useProjects.getState();
    const available = projects.activeId === projectId && projects.projects.some(project => project.id === projectId);
    if (snapshot.available !== available) snapshot = available ? { kind: "composer", available: true, capabilities } : { kind: "composer", available: false, reason: "Open this file's project first.", capabilities };
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
    return { status: "added", partIds: accepted.partIds };
  };
  const offer = (context: PromptContext, workspace: string, projectPath: string) => {
    const operationId = context.operationId;
    let retained: PromptContext | null = context;
    let starting = false;
    let released = false;
    let toastId: ReturnType<typeof toast.error> | undefined;
    const release = () => {
      if (released) return;
      released = true;
      retained = null;
      pendingOffers.delete(operationId);
      operations.delete(operationId);
      if (toastId !== undefined) toast.dismiss(toastId);
    };
    pendingOffers.get(operationId)?.release();
    while (pendingOffers.size >= 8) pendingOffers.values().next().value!.release();
    pendingOffers.set(operationId, { release });
    const show = () => { toastId = toast.error("This context belongs to another workspace.", {
      description: workspace, duration: Infinity,
      onDismiss: release,
      action: { label: "Start chat here", onClick: () => {
        if (starting || !retained) return;
        if (Object.hasOwn(useComposer.getState().acceptedContexts, operationId)) { release(); return; }
        const project = useProjects.getState().projects.find(item => item.id === projectId);
        if (!project || project.path !== projectPath) { toast.error("This context's project is no longer available."); return; }
        starting = true;
        const activeProject = useProjects.getState().activeId;
        const activeSession = useSessions.getState().activeId;
        void materialize(retained).then(async parts => {
          if (!retained) return;
          const currentProject = useProjects.getState().projects.find(item => item.id === projectId);
          if (!currentProject || currentProject.path !== projectPath) throw new Error("This context's project is no longer available.");
          const session = await useSessions.getState().start({ projectId, cwd: workspace }, { select: false });
          if (!retained) return;
          if (session.projectId !== projectId || session.cwd !== workspace) throw new Error("The new chat did not open in this context's workspace.");
          validateDraftDestination({ key: session.id, projectId, projectPath, workspace, kind: "session" });
          const focus = useProjects.getState().activeId === activeProject && useSessions.getState().activeId === activeSession;
          if (focus) { useProjects.getState().setActive(projectId); useSessions.getState().setActive(session.id); }
          useComposer.getState().acceptContext(session.id, operationId, parts, { root: workspace, focus });
          release();
        }).catch(error => { starting = false; toast.error(message(error)); if (retained) show(); });
      } },
    }); };
    show();
  };
  return {
    getSnapshot,
    subscribe: listener => {
      const unsubscribes = [useProjects.subscribe(listener), useSessions.subscribe(listener), useComposer.subscribe(listener)];
      return () => unsubscribes.forEach(unsubscribe => unsubscribe());
    },
    deliver(context) {
      consumeAttachmentRejections(context);
      try { validatePromptContext(context); }
      catch (error) { return Promise.resolve({ status: "failed", message: message(error) }); }
      const receipts = useComposer.getState().acceptedContexts;
      const accepted = Object.hasOwn(receipts, context.operationId) ? receipts[context.operationId] : undefined;
      if (accepted) return Promise.resolve({ status: "added", partIds: accepted.partIds });
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
        // This happens synchronously before an attachment promise can resolve.
        let destination: DraftDestination;
        try { destination = bindDraftDestination(projectId, root); }
        catch (error) {
          if (!(error instanceof WorkspaceMismatch)) throw error;
          const project = useProjects.getState().projects.find(item => item.id === projectId)!;
          offer(frozen, root ?? project.path, project.path);
          operation = Promise.resolve({ status: "deferred", message: message(error) });
          return remember(context.operationId, operation);
        }
        operation = accept(frozen, destination).catch(error => {
          if (error instanceof WorkspaceMismatch) offer(frozen, destination.workspace, destination.projectPath);
          return { status: error instanceof DraftDestinationGone || (error instanceof Error && error.name === "AbortError") ? "cancelled" : error instanceof WorkspaceMismatch ? "deferred" : "failed", message: message(error) };
        });
      } catch (error) { operation = Promise.resolve({ status: "failed", message: message(error) }); }
      return remember(context.operationId, operation);
    },
  };
}
