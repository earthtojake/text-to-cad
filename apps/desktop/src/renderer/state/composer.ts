import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import { useAcp } from "./acp";
import { parseSegments } from "../features/session/composer/references";
import type { PromptBlock } from "@shared/acp/types";
import { referenceText, type CadReference } from "@shared/cad-refs";
import type { PromptReference } from "@hardcore/core/prompt";

/**
 * What the composer holds that is not yet a turn: the queue of prompts
 * submitted while a turn was running (Codex sends them one after another
 * when the agent is free), and each session's unsent draft so switching
 * sessions and back does not lose typed text.
 *
 * Sending is the store's job rather than a component's so the queue drains
 * even when the session pane has re-rendered or the user has moved on to
 * another session: `drain` is called from the bridge whenever a session goes
 * idle.
 *
 * The explorer writes into the composer too (item 4 of the CAD review): a
 * reference added from the viewer lands in the draft as its token, which the
 * editor draws as a chip (`features/session/composer`), and a capture of the
 * viewport is queued as a file for the composer's attachments to pick up —
 * they live inside AI Elements' `PromptInput`, which nothing outside it can
 * reach directly, so `pendingFiles` is the hand-off.
 */
export type QueuedPrompt = {
  id: string;
  /** The text the user typed, for the queue's row. */
  text: string;
  content: PromptBlock[];
};

/** The draft key for a session, or for the new-session state. */
export const NEW_SESSION_KEY = "__new__";
export const newSessionKey = (projectId: string) => `${NEW_SESSION_KEY}:${projectId}`;

export type DraftContext = { text?: string; references?: CadReference[]; files?: File[]; deduplicateText?: boolean };
export type DraftPart =
  | { id: string; kind: "text"; text: string }
  | { id: string; kind: "reference"; text: string; label?: string; reference?: PromptReference }
  | { id: string; kind: "attachment"; file: File; about?: readonly string[] }
  | { id: string; kind: "annotation"; references: DraftAnnotationReference[]; text: string };
/** A reference an annotation is about: its prompt token (`file#selector`) and the chip's label. */
export type DraftAnnotationReference = { text: string; label?: string };
/**
 * A note the person pinned to geometry in the viewer and added to this draft. Annotations ride
 * beside the text as one chip until the prompt is sent, then go out as a numbered list.
 */
export type DraftAnnotation = { id: string; references: DraftAnnotationReference[]; text: string };
export type AcceptedContext = {
  key: string; partIds: string[];
  /** Snapshot identities and ordering remain available without retaining binary content. */
  parts: { id: string; kind: DraftPart["kind"]; reference?: PromptReference; about?: readonly string[] }[];
};

type ComposerState = {
  focusRequest: { key: string; nonce: number } | null;
  addContext: (key: string, context: DraftContext) => void;
  /** A complete validated bundle is accepted in one store transaction, never submitted. */
  acceptContext: (key: string, operationId: string, parts: readonly DraftPart[], options: { root: string; focus: boolean }) => AcceptedContext;
  acceptedContexts: Record<string, AcceptedContext>;
  queues: Record<string, QueuedPrompt[]>;
  drafts: Record<string, string>;
  /** Display metadata belongs to the draft, not to another project's identical token. */
  referenceLabels: Record<string, Record<string, string>>;
  /** Annotations added from the viewer, per draft key, until the prompt is sent. */
  annotations: Record<string, DraftAnnotation[]>;
  removeAnnotations: (key: string) => void;
  /** Files the explorer attached, per draft key, until the composer takes them. */
  pendingFiles: Record<string, File[]>;
  /** A new draft with a CAD reference runs in that model’s workspace. */
  draftRoots: Record<string, string>;
  setDraftRoot: (key: string, root: string | undefined) => void;

  /** Send now when the session is idle; queue it otherwise. */
  submit: (sessionId: string, text: string, content: PromptBlock[]) => Promise<void>;
  enqueue: (sessionId: string, text: string, content: PromptBlock[]) => void;
  dequeue: (sessionId: string, id: string) => QueuedPrompt | null;
  clearQueue: (sessionId: string) => void;
  /** Send the next queued prompt if the session is idle. */
  drain: (sessionId: string) => Promise<void>;
  setDraft: (sessionId: string, text: string) => void;
  /** Append a reference to a draft, as its token, spaced from what is there. */
  insertReference: (key: string, reference: CadReference) => void;
  /** Queue a file for a draft's attachments. */
  attachFile: (key: string, file: File) => void;
  /** The composer takes what was queued for it. */
  takeFiles: (key: string) => File[];
};

let sequence = 0;

export const useComposer = create<ComposerState>((set, get) => ({
  focusRequest: null,
  acceptedContexts: {},
  acceptContext: (key, operationId, parts, options) => {
    const receipts = get().acceptedContexts;
    const previous = Object.hasOwn(receipts, operationId) ? receipts[operationId] : undefined;
    if (previous) return previous;
    const accepted = { key, partIds: parts.map(part => part.id), parts: parts.map(part => ({
      id: part.id, kind: part.kind,
      ...(part.kind === "reference" && part.reference ? { reference: structuredClone(part.reference) } : {}),
      ...(part.kind === "attachment" && part.about ? { about: [...part.about] } : {}),
    })) };
    // What an attachment is about. A viewer snapshot with nothing selected is about the whole
    // file it shows, and names it only so the image has a subject — which a draft that already
    // names that file, down to any part or face of it, has: the image is about the file either
    // way, and a second, bare token for it would be noise beside the one the person chose.
    const subjects = new Set(parts.flatMap(part => part.kind === "attachment" ? part.about ?? [] : []));
    set(state => {
      let text = state.drafts[key] ?? "";
      const labels = { ...state.referenceLabels[key] };
      const files = [...(state.pendingFiles[key] ?? [])];
      // An annotation added again (edited since) replaces its earlier copy rather than repeating it.
      const annotations = [...(state.annotations[key] ?? [])];
      for (const part of parts) {
        if (part.kind === "attachment") { files.push(part.file); continue; }
        if (part.kind === "annotation") {
          const annotation = { id: part.id, references: part.references.map(reference => ({ ...reference })), text: part.text };
          const index = annotations.findIndex(existing => existing.id === part.id);
          if (index >= 0) annotations[index] = annotation; else annotations.push(annotation);
          continue;
        }
        if (part.kind === "reference") {
          const named = parseSegments(text).flatMap(segment => segment.type === "reference" ? [segment.reference] : []);
          const subjectNamed = subjects.has(part.id) && part.reference?.target.kind === "whole-resource"
            && named.some(reference => referenceText({ file: reference.file, selector: "" }) === part.text);
          if (!subjectNamed && !named.some(reference => referenceText(reference) === part.text)) {
            text += `${text && !/\s$/.test(text) ? " " : ""}${part.text} `;
          }
          if (part.label?.trim()) labels[part.text] = part.label.trim();
        } else if (part.text) {
          text += `${text.trim() ? "\n\n" : ""}${part.text}`;
        }
      }
      return {
        drafts: { ...state.drafts, [key]: text },
        referenceLabels: { ...state.referenceLabels, [key]: labels },
        pendingFiles: { ...state.pendingFiles, [key]: files },
        annotations: { ...state.annotations, [key]: annotations },
        draftRoots: { ...state.draftRoots, [key]: options.root },
        // Receipts contain no attachment bytes and retain only recent operations.
        acceptedContexts: Object.fromEntries([...Object.entries(state.acceptedContexts), [operationId, accepted]].slice(-256)),
        ...(options.focus ? { focusRequest: { key, nonce: ++sequence } } : {}),
      };
    });
    return accepted;
  },
  addContext: (key, context) => set((state) => {
    let text = state.drafts[key] ?? "";
    const labels = { ...state.referenceLabels[key] };
    for (const reference of context.references ?? []) {
      const token = referenceText(reference);
      if (!parseSegments(text).some(segment => segment.type === "reference" && referenceText(segment.reference) === token)) text += `${text && !/\s$/.test(text) ? " " : ""}${token} `;
      if (reference.label?.trim()) labels[token] = reference.label.trim();
    }
    if (context.text && !(context.deduplicateText && text.includes(context.text))) text += `${text.trim() ? "\n\n" : ""}${context.text}`;
    return {
      drafts: { ...state.drafts, [key]: text },
      referenceLabels: { ...state.referenceLabels, [key]: labels },
      pendingFiles: { ...state.pendingFiles, [key]: [...(state.pendingFiles[key] ?? []), ...(context.files ?? [])] },
      focusRequest: { key, nonce: ++sequence },
    };
  }),
  queues: {},
  drafts: {},
  referenceLabels: {},
  annotations: {},
  removeAnnotations: (key) => set(state => {
    const { [key]: _removed, ...rest } = state.annotations;
    return { annotations: rest };
  }),
  pendingFiles: {},
  draftRoots: {},
  setDraftRoot: (key, root) => set((state) => {
    const roots = { ...state.draftRoots };
    if (root) roots[key] = root; else delete roots[key];
    return { draftRoots: roots };
  }),

  submit: async (sessionId, text, content) => {
    const status = useAcp.getState().sessions[sessionId]?.status;
    if (status === "running" || status === "waiting") {
      get().enqueue(sessionId, text, content);
      return;
    }
    await send(sessionId, content);
  },

  enqueue: (sessionId, text, content) =>
    set((state) => ({
      queues: {
        ...state.queues,
        [sessionId]: [...(state.queues[sessionId] ?? []), { id: `q${++sequence}`, text, content }],
      },
    })),

  dequeue: (sessionId, id) => {
    const queue = get().queues[sessionId] ?? [];
    const item = queue.find((candidate) => candidate.id === id) ?? null;
    if (item) {
      set((state) => ({
        queues: { ...state.queues, [sessionId]: queue.filter((candidate) => candidate.id !== id) },
      }));
    }
    return item;
  },

  clearQueue: (sessionId) =>
    set((state) => ({ queues: { ...state.queues, [sessionId]: [] } })),

  drain: async (sessionId) => {
    const next = get().queues[sessionId]?.[0];
    const status = useAcp.getState().sessions[sessionId]?.status;
    if (!next || status !== "idle") {
      return;
    }
    get().dequeue(sessionId, next.id);
    await send(sessionId, next.content);
  },

  setDraft: (sessionId, text) =>
    set((state) => {
      const roots = { ...state.draftRoots };
      const labels = { ...state.referenceLabels };
      if (!text.trim()) delete roots[sessionId];
      if (!text.trim()) delete labels[sessionId];
      return { drafts: { ...state.drafts, [sessionId]: text }, draftRoots: roots, referenceLabels: labels };
    }),

  insertReference: (key, reference) =>
    set((state) => {
      const current = state.drafts[key] ?? "";
      const token = referenceText(reference);
      const separator = current === "" || /\s$/.test(current) ? "" : " ";
      const labels = { ...state.referenceLabels[key] };
      if (reference.label?.trim()) labels[token] = reference.label.trim(); else delete labels[token];
      return { drafts: { ...state.drafts, [key]: `${current}${separator}${token} ` }, referenceLabels: { ...state.referenceLabels, [key]: labels } };
    }),

  attachFile: (key, file) =>
    set((state) => ({ pendingFiles: { ...state.pendingFiles, [key]: [...(state.pendingFiles[key] ?? []), file] } })),

  takeFiles: (key) => {
    const files = get().pendingFiles[key] ?? [];
    if (files.length > 0) {
      set((state) => {
        const { [key]: _taken, ...rest } = state.pendingFiles;
        return { pendingFiles: rest };
      });
    }
    return files;
  },
}));

/**
 * `prompt` resolves when the turn ends and rejects when the agent refuses
 * it. The rejection is already in the transcript (the reducer's
 * `prompt/error` part), so nothing else needs to see it here.
 */
async function send(sessionId: string, content: PromptBlock[]) {
  try {
    await useAcp.getState().prompt(sessionId, content);
  } catch {
    // Reported in the transcript with a Retry.
  }
  await useComposer.getState().drain(sessionId);
}

export function useQueue(sessionId: string | null): QueuedPrompt[] {
  return useComposer(useShallow((state) => (sessionId ? (state.queues[sessionId] ?? []) : [])));
}
