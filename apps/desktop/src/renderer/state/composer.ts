import { toast } from "sonner";
import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import { PromptRefused, useAcp } from "./acp";
import { useSessions } from "./sessions";
import { parseSegments } from "../features/session/composer/references";
import type { PromptBlock } from "@shared/acp/types";
import { referenceText, type CadReference } from "@shared/cad-refs";
import { errorMessage } from "@shared/ipc/errors";
import { withoutKey } from "@renderer/lib/record";
import type { PromptReference } from "@text-to-cad/core/prompt";

/**
 * What the composer holds that is not yet a turn: the queue of prompts
 * submitted while a turn was running (Codex sends them one after another
 * when the agent is free), and each session's unsent draft so switching
 * sessions and back does not lose typed text.
 *
 * Sending is the store's job rather than a component's so the queue drains
 * even when the session pane has re-rendered or the user has moved on to
 * another session. The queue is driven from the bridge only: it hands every
 * `prompt/start`, `prompt/end` and `prompt/error` to `turnEvent`, and a turn
 * that ends is what sends the next queued prompt (plus the reconnect below, and
 * a `session.update` of any other kind that takes the status from non-idle to
 * idle: a permission asked outside a turn and answered ends with no `prompt/end`).
 * The `prompt` reply does not drain — it arrives after main has already broadcast `prompt/end`, so a
 * second drain there would send the prompt after the one the bridge just sent,
 * and main runs whatever turns it is handed.
 *
 * One prompt is in flight per session. `sending` is set synchronously when a
 * prompt goes out and cleared by that turn's `prompt/start` (from then on the
 * session's own status says it is busy), by `prompt/end`/`prompt/error`, or by
 * the IPC rejecting before main dispatched anything. A prompt submitted while
 * one is in flight is queued behind it.
 *
 * The one other driver is a reconnect: an agent evicted or disconnected with
 * prompts queued comes back through a `session.state` snapshot, never a
 * `prompt/end`, so the bridge drains when a snapshot says the session is idle
 * (`drain` is a no-op when a prompt is already in flight), as it does when a
 * `session.update` leaves the status idle after it was not. A prompt submitted
 * behind that queue while the agent is gone joins it and asks the agent back
 * (`ensureLoaded`), so the reconnect sends the queue in the order it was typed;
 * if the agent does not come back, the queue's head is sent anyway so it fails
 * in the transcript with a Retry instead of waiting silently.
 *
 * A failed turn pauses the queue. The failure is in the transcript with its
 * Retry, and what the person sends next — that Retry, or a new prompt — goes
 * out at once, ahead of the queue; the queue resumes when that turn ends.
 * `paused` carries that across an eviction or reconnect, which a session's
 * status alone (closed, then idle) does not remember. The queue row says it is
 * paused and offers Resume (`resume`) for a Retry refused before any turn began
 * or one never sent; clearing or emptying the queue lifts the pause too.
 * Sending the queue on into an agent that just failed would fail each queued
 * prompt in turn, and a Retry that waited behind the queue would answer the
 * failed prompt out of order.
 *
 * The explorer writes into the composer too (item 4 of the CAD review): a
 * reference added from the viewer lands in the draft as its token, which the
 * editor draws as a chip (`features/session/composer`), and a capture of the
 * viewport is queued as a file for the composer's attachments to pick up —
 * they live inside AI Elements' `PromptInput`, which nothing outside it can
 * reach directly, so `pendingFiles` is the hand-off.
 *
 * What is held here lives as long as the session's row in the index. A row
 * the index no longer lists (a deleted session) takes its queue, draft,
 * reference labels, annotations, pending files and flags with it (`forget`,
 * called from the index subscription at the foot of this file); an archived
 * row keeps them, because archiving does not spend what was typed.
 */
export type QueuedPrompt = {
  id: string;
  /** The text the user typed, for the queue's row. */
  text: string;
  content: PromptBlock[];
  /** The draft it was sent from, so removing it from the queue puts that back as it was. */
  draft?: TakenDraft;
};

/**
 * A draft as the composer took it on submit: the typed text and the annotations beside it kept
 * apart (the prompt is their flattening, and cannot be split back), with what the text's chips
 * and workspace hang on. `restoreDraft` puts it back when the prompt does not go out.
 */
export type TakenDraft = {
  text: string;
  annotations: DraftAnnotation[];
  labels?: Record<string, string>;
  root?: string;
  /**
   * The box's attachments, as files: the strip empties when the prompt is accepted, not when
   * its turn ends, so a prompt refused afterwards — queued, sent from the new-session screen
   * into the session it made, or sent straight from the box — has only these to get them back.
   * `restoreDraft` attaches them again.
   */
  files?: File[];
};

/** The draft key for a session, or for the new-session state. */
export const NEW_SESSION_KEY = "__new__";
export const newSessionKey = (projectId: string) => `${NEW_SESSION_KEY}:${projectId}`;

export type DraftContext = { text?: string; references?: CadReference[]; files?: File[]; deduplicateText?: boolean };
export type DraftPart =
  | { id: string; kind: "text"; text: string }
  | { id: string; kind: "reference"; text: string; label?: string; reference?: PromptReference }
  | { id: string; kind: "attachment"; file: File; about?: readonly string[] }
  | { id: string; kind: "annotation"; references: PromptReference[]; text: string; attachments?: string[] };
/**
 * A note the person pinned to geometry in the viewer, in this draft. Annotations ride beside the
 * text as one chip until the prompt is sent, then go out as a numbered list after it. A note on a
 * sketch keeps the sketch (`image`): it is shown with the note and sent with it, not as a loose
 * attachment in the strip.
 */
export type DraftAnnotation = { id: string; references: PromptReference[]; text: string; image?: File };
export type AcceptedContext = {
  key: string; partIds: string[];
  /** Snapshot identities and ordering remain available without retaining binary content. */
  parts: { id: string; kind: DraftPart["kind"]; reference?: PromptReference; about?: readonly string[] }[];
};

type ComposerState = {
  focusRequest: { key: string; nonce: number } | null;
  /** Put the caret in that box, for a control that answers something and then leaves the page. */
  requestFocus: (key: string) => void;
  /**
   * A send asked for from outside the composer — the new-session state's Try again — so what goes
   * out is what the box holds now, attachments included, exactly as Enter would send it. The
   * composer consumes it (`consumeSubmit`) when it acts on it: left in place, a composer for the
   * same key arriving later (New session for another project and back) would send its box unasked.
   */
  submitRequest: { key: string; nonce: number } | null;
  requestSubmit: (key: string) => void;
  /** Clear the request if it is still the one handled; a newer request stays. */
  consumeSubmit: (nonce: number) => void;
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
  /** All of a draft's annotations, or only those with the given ids. */
  removeAnnotations: (key: string, ids?: readonly string[]) => void;
  /**
   * A note rewritten in the composer's own list. The viewer's copy follows through the
   * destination's `heldText`, so nothing is delivered back. An empty note is not an edit.
   */
  editAnnotation: (key: string, id: string, text: string) => void;
  /** Files the explorer attached, per draft key, until the composer takes them. */
  pendingFiles: Record<string, File[]>;
  /** A new draft with a CAD reference runs in that model’s workspace. */
  draftRoots: Record<string, string>;
  setDraftRoot: (key: string, root: string | undefined) => void;

  /**
   * Send now when the session is free; queue it behind a running turn, a prompt already in
   * flight, or a queue that is still draining. After a failed turn it goes out at once.
   */
  submit: (sessionId: string, text: string, content: PromptBlock[], draft?: TakenDraft) => Promise<void>;
  enqueue: (sessionId: string, text: string, content: PromptBlock[], draft?: TakenDraft) => void;
  dequeue: (sessionId: string, id: string) => QueuedPrompt | null;
  clearQueue: (sessionId: string) => void;
  /** Send the next queued prompt if the session is idle and nothing is in flight. */
  drain: (sessionId: string, options?: { evenIfNotIdle?: boolean }) => Promise<void>;
  /** Lift a failure's pause by hand (the queue's Resume) and send what is next. */
  resume: (sessionId: string) => Promise<void>;
  /** Sessions with a prompt sent and no `prompt/start` for it yet, by send token. */
  sending: Record<string, number>;
  /**
   * Sessions whose last turn failed: the queue holds until the next turn starts, and what is sent
   * meanwhile — the Retry or a new prompt — goes out first, even after the agent was evicted.
   */
  paused: Record<string, true>;
  /** The bridge's hand-off of a turn's lifecycle events: the queue's one driver. */
  turnEvent: (sessionId: string, type: "prompt/start" | "prompt/end" | "prompt/error") => void;
  /** Clear a draft for sending, returning what it held. */
  takeDraft: (key: string) => TakenDraft;
  /**
   * Put a taken draft back, ahead of anything written into the box since — or after it (`behind`),
   * for a queued prompt refused after those ahead of it were put back, so the box reads in the
   * order they were queued.
   */
  restoreDraft: (key: string, draft: TakenDraft, options?: { behind?: boolean }) => void;
  setDraft: (sessionId: string, text: string) => void;
  /** Append a reference to a draft, as its token, spaced from what is there. */
  insertReference: (key: string, reference: CadReference) => void;
  /** Queue a file for a draft's attachments. */
  attachFile: (key: string, file: File) => void;
  /** The composer takes what was queued for it. */
  takeFiles: (key: string) => File[];
  /** Everything held for a session whose row is gone: its queue, draft, notes, files and flags. */
  forget: (sessionId: string) => void;
};

let sequence = 0;

export const useComposer = create<ComposerState>((set, get) => ({
  focusRequest: null,
  requestFocus: (key) => set({ focusRequest: { key, nonce: ++sequence } }),
  submitRequest: null,
  requestSubmit: (key) => set({ submitRequest: { key, nonce: ++sequence } }),
  consumeSubmit: (nonce) => set((state) => state.submitRequest?.nonce === nonce ? { submitRequest: null } : state),
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
      let annotations = state.annotations[key];
      // An attachment an annotation names is that annotation's (a sketch), not the strip's.
      const claimed = new Map(parts.flatMap(part => part.kind === "annotation" ? (part.attachments ?? []).map(id => [id, part.id]) : []));
      const attachmentsById = new Map(parts.flatMap(part => part.kind === "attachment" ? [[part.id, part.file]] : []));
      for (const part of parts) {
        if (part.kind === "attachment") { if (!claimed.has(part.id)) files.push(part.file); continue; }
        if (part.kind === "annotation") {
          const image = (part.attachments ?? []).map(id => attachmentsById.get(id)).find(file => file?.type.startsWith("image/"));
          const annotation = { id: part.id, references: structuredClone(part.references), text: part.text, ...(image ? { image } : {}) };
          annotations = [...(annotations ?? []).filter(existing => existing.id !== part.id), annotation];
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
        ...(annotations !== state.annotations[key] ? { annotations: { ...state.annotations, [key]: annotations ?? [] } } : {}),
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
  editAnnotation: (key, id, text) => set(state => {
    const value = text.trim();
    const current = state.annotations[key];
    const target = current?.find(annotation => annotation.id === id);
    if (!value || !target || target.text === value) return state;
    return { annotations: { ...state.annotations, [key]: current!.map(annotation => annotation.id === id ? { ...annotation, text: value } : annotation) } };
  }),
  removeAnnotations: (key, ids) => set(state => {
    const current = state.annotations[key];
    const kept = ids ? current?.filter(annotation => !ids.includes(annotation.id)) : undefined;
    if (!current || kept?.length === current.length) return state;
    if (kept) return { annotations: { ...state.annotations, [key]: kept } };
    return { annotations: withoutKey(state.annotations, key) };
  }),
  pendingFiles: {},
  draftRoots: {},
  setDraftRoot: (key, root) => set((state) => {
    const roots = { ...state.draftRoots };
    if (root) roots[key] = root; else delete roots[key];
    return { draftRoots: roots };
  }),

  submit: async (sessionId, text, content, draft) => {
    const status = useAcp.getState().sessions[sessionId]?.status;
    const queued = (get().queues[sessionId]?.length ?? 0) > 0;
    const busy = status === "running" || status === "waiting" || sessionId in get().sending;
    // The queue waits on an idle session that is still draining it. After a failed turn it is
    // paused and this goes first (see the header). With no live agent — closed, connecting, never
    // loaded — this joins the queue and the agent is asked back: the reconnect's idle snapshot
    // drains the queue in order. Sent now, it would hold `sending` through the reconnect and the
    // prompts queued before it would go out after it.
    const gone = status === "closed" || status === "connecting" || status === undefined;
    if (busy || (queued && !(sessionId in get().paused) && (status === "idle" || gone))) {
      get().enqueue(sessionId, text, content, draft);
      if (!busy && gone) {
        await reconnectAndDrain(sessionId);
        return;
      }
      await get().drain(sessionId);
      return;
    }
    // Only a send with a draft is the composer's, which puts the draft back on a rejection: a
    // refusal for what it holds, or main refusing it before any turn (see `send`).
    await send(sessionId, content, undefined, { rethrowRefusal: draft !== undefined });
  },

  enqueue: (sessionId, text, content, draft) =>
    set((state) => ({
      queues: {
        ...state.queues,
        [sessionId]: [...(state.queues[sessionId] ?? []), { id: `q${++sequence}`, text, content, ...(draft ? { draft } : {}) }],
      },
    })),

  dequeue: (sessionId, id) => {
    const queue = get().queues[sessionId] ?? [];
    const item = queue.find((candidate) => candidate.id === id) ?? null;
    if (item) {
      const rest = queue.filter((candidate) => candidate.id !== id);
      set((state) => ({
        queues: { ...state.queues, [sessionId]: rest },
        // Nothing left to hold back: an emptied queue is not paused.
        ...(rest.length === 0 ? { paused: withoutKey(state.paused, sessionId) } : {}),
      }));
    }
    return item;
  },

  clearQueue: (sessionId) =>
    set((state) => ({ queues: { ...state.queues, [sessionId]: [] }, paused: withoutKey(state.paused, sessionId) })),

  resume: async (sessionId) => {
    set((state) => ({ paused: withoutKey(state.paused, sessionId) }));
    const status = useAcp.getState().sessions[sessionId]?.status;
    // "error" is where Resume is shown: a failed turn leaves the session there, and plain `drain`
    // waits for idle, so it goes the way an unreachable agent does and the head is sent anyway.
    if (status === "error" || status === "closed" || status === "connecting" || status === undefined) {
      await reconnectAndDrain(sessionId);
      return;
    }
    await get().drain(sessionId);
  },

  drain: async (sessionId, options) => {
    const next = get().queues[sessionId]?.[0];
    const status = useAcp.getState().sessions[sessionId]?.status;
    if (!next || (status !== "idle" && !options?.evenIfNotIdle) || sessionId in get().sending || sessionId in get().paused) {
      return;
    }
    get().dequeue(sessionId, next.id);
    await send(sessionId, next.content, next);
  },

  sending: {},
  paused: {},
  turnEvent: (sessionId, type) => {
    clearSending(sessionId);
    if (type === "prompt/error") set((state) => ({ paused: { ...state.paused, [sessionId]: true } }));
    if (type === "prompt/start" && sessionId in get().paused) {
      set((state) => ({ paused: withoutKey(state.paused, sessionId) }));
    }
    // A turn that starts is an agent that came back: a refusal `send` showed is over.
    if (type === "prompt/start" && sessionId in useAcp.getState().loadErrors) {
      useAcp.setState((state) => ({ loadErrors: withoutKey(state.loadErrors, sessionId) }));
    }
    if (type === "prompt/end") void get().drain(sessionId);
  },

  takeDraft: (key) => {
    const state = get();
    const labels = state.referenceLabels[key];
    const root = state.draftRoots[key];
    const taken: TakenDraft = {
      text: state.drafts[key] ?? "",
      annotations: state.annotations[key] ?? [],
      ...(labels && Object.keys(labels).length ? { labels: { ...labels } } : {}),
      ...(root ? { root } : {}),
    };
    get().setDraft(key, "");
    get().removeAnnotations(key);
    return taken;
  },

  restoreDraft: (key, draft, options) => set((state) => {
    const current = state.drafts[key] ?? "";
    const [first, second] = options?.behind ? [current, draft.text] : [draft.text, current];
    const text = !second.trim() ? first : !first.trim() ? second : `${first}\n\n${second}`;
    const since = (state.annotations[key] ?? []).filter(annotation => !draft.annotations.some(taken => taken.id === annotation.id));
    const annotations = options?.behind ? [...since, ...draft.annotations] : [...draft.annotations, ...since];
    return {
      drafts: { ...state.drafts, [key]: text },
      ...(annotations.length ? { annotations: { ...state.annotations, [key]: annotations } } : {}),
      ...(draft.labels ? { referenceLabels: { ...state.referenceLabels, [key]: { ...draft.labels, ...state.referenceLabels[key] } } } : {}),
      ...(draft.root && !state.draftRoots[key] ? { draftRoots: { ...state.draftRoots, [key]: draft.root } } : {}),
      ...(draft.files?.length ? { pendingFiles: { ...state.pendingFiles, [key]: [...(state.pendingFiles[key] ?? []), ...draft.files] } } : {}),
    };
  }),

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
      set((state) => ({ pendingFiles: withoutKey(state.pendingFiles, key) }));
    }
    return files;
  },

  forget: (sessionId) => set((state) => ({
    queues: withoutKey(state.queues, sessionId),
    drafts: withoutKey(state.drafts, sessionId),
    referenceLabels: withoutKey(state.referenceLabels, sessionId),
    annotations: withoutKey(state.annotations, sessionId),
    pendingFiles: withoutKey(state.pendingFiles, sessionId),
    draftRoots: withoutKey(state.draftRoots, sessionId),
    sending: withoutKey(state.sending, sessionId),
    paused: withoutKey(state.paused, sessionId),
    acceptedContexts: Object.fromEntries(Object.entries(state.acceptedContexts).filter(([, context]) => context.key !== sessionId)),
  })),
}));

/**
 * The index decides what is kept here, as it does for the acp store: a deleted row takes its queue
 * (Files and their base64 blocks), draft, notes and their sketches with it — nothing else ever
 * would. An archived row keeps them: what was typed is not spent by archiving, and it comes back.
 */
useSessions.subscribe((index, previous) => {
  if (index.sessions === previous.sessions) return;
  const rows = new Set(index.sessions.map((row) => row.id));
  for (const row of previous.sessions) {
    if (!rows.has(row.id)) useComposer.getState().forget(row.id);
  }
});

/**
 * `prompt` resolves when the turn ends and rejects when the agent refuses
 * it. The rejection is already in the transcript (the reducer's
 * `prompt/error` part), so nothing else needs to see it here. The next queued
 * prompt is not sent from here: `prompt/end` has already done that.
 */
async function send(sessionId: string, content: PromptBlock[], item?: QueuedPrompt, options?: { rethrowRefusal?: boolean }) {
  const token = ++sequence;
  // Synchronously, before the IPC: until main dispatches `prompt/start` the
  // session's status still reads idle, and this is what says it is not.
  useComposer.setState((state) => ({ sending: { ...state.sending, [sessionId]: token } }));
  try {
    await useAcp.getState().prompt(sessionId, content);
  } catch (error) {
    // A rejection after the turn began is in the transcript with a Retry (the
    // `prompt/error` part), and that turn event has already cleared `sending`.
    // Still ours means main refused before any turn event — the agent could not
    // be brought back (not installed, signed out, its folder gone) — and the
    // transcript never saw the prompt. The reason is shown where a failed
    // reconnect is (`loadErrors`, with its Retry), and the prompt does not
    // vanish: a queued one goes back at the head with the queue paused, one
    // sent from the box rejects so the composer puts the draft back.
    const refusedUnseen = useComposer.getState().sending[sessionId] === token;
    clearSending(sessionId, token);
    // The row was deleted while the prompt was out (`forget` has run, and took `sending` with it,
    // so the unseen refusal below is already out of reach): a refusal's put-back written now
    // would be a draft for a session nothing will forget again. Before the index has loaded a
    // missing row proves nothing, as in the bridge's `session.state`.
    const index = useSessions.getState();
    if (index.ready && !index.sessions.some((row) => row.id === sessionId)) return;
    // Refused for what it holds — a block the agent did not say it takes — and not because the
    // agent is gone: no turn began, nothing failed, and a Retry or a Reconnect would change
    // nothing. The reason is said the way `refuseSend`'s is, and what was written is not spent:
    // a send from the box rejects so the composer puts the draft back with its attachments; a
    // queued one goes back into the box as it was taken, and the queue goes on behind it.
    if (error instanceof PromptRefused) {
      toast.info(error.message);
      if (options?.rethrowRefusal) throw error;
      // After any put back before it, in queue order; one queued with no draft (the transcript's
      // Retry behind a running turn) goes back as the text its row showed.
      if (item) useComposer.getState().restoreDraft(sessionId, item.draft ?? { text: item.text, annotations: [] }, { behind: true });
      if (item) void useComposer.getState().drain(sessionId);
      return;
    }
    if (!refusedUnseen) return;
    if (item) {
      useComposer.setState((state) => ({
        queues: { ...state.queues, [sessionId]: [item, ...(state.queues[sessionId] ?? [])] },
        paused: { ...state.paused, [sessionId]: true },
      }));
    }
    useAcp.setState((state) => ({ loadErrors: { ...state.loadErrors, [sessionId]: errorMessage(error) } }));
    // Sent straight from the box (nothing queued, the agent closed or failed): no queue holds it,
    // so the rejection goes back to the composer, which puts the draft back with its attachments.
    if (!item && options?.rethrowRefusal) throw error;
  }
}

/**
 * The queue on a session with no live agent: ask it back, then drain. A live connection main
 * still holds sends no fresh snapshot, so this drains once `ensureLoaded` settles too. If the agent
 * did not come back — still closed or failed, or no session at all, and no load on its way — the
 * queue's head goes out anyway, so it fails in the transcript with a Retry rather than waiting
 * silently. A busy or connecting agent (a live snapshot painted, a connect main is driving) is
 * never handed it.
 */
async function reconnectAndDrain(sessionId: string) {
  await useAcp.getState().ensureLoaded(sessionId).catch(() => undefined);
  const acp = useAcp.getState();
  const status = acp.sessions[sessionId]?.status;
  const unreachable = status === "closed" || status === "error" || status === undefined;
  await useComposer.getState().drain(sessionId, { evenIfNotIdle: unreachable && !acp.loading[sessionId] });
}

function clearSending(sessionId: string, token?: number) {
  useComposer.setState((state) => {
    if (!(sessionId in state.sending) || (token !== undefined && state.sending[sessionId] !== token)) return state;
    return { sending: withoutKey(state.sending, sessionId) };
  });
}

export function useQueue(sessionId: string | null): QueuedPrompt[] {
  return useComposer(useShallow((state) => (sessionId ? (state.queues[sessionId] ?? []) : [])));
}
