import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import { useAcp } from "./acp";
import type { PromptBlock } from "@shared/acp/types";

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
 */
export type QueuedPrompt = {
  id: string;
  /** The text the user typed, for the queue's row. */
  text: string;
  content: PromptBlock[];
};

type ComposerState = {
  queues: Record<string, QueuedPrompt[]>;
  drafts: Record<string, string>;

  /** Send now when the session is idle; queue it otherwise. */
  submit: (sessionId: string, text: string, content: PromptBlock[]) => Promise<void>;
  enqueue: (sessionId: string, text: string, content: PromptBlock[]) => void;
  dequeue: (sessionId: string, id: string) => QueuedPrompt | null;
  clearQueue: (sessionId: string) => void;
  /** Send the next queued prompt if the session is idle. */
  drain: (sessionId: string) => Promise<void>;
  setDraft: (sessionId: string, text: string) => void;
};

let sequence = 0;

export const useComposer = create<ComposerState>((set, get) => ({
  queues: {},
  drafts: {},

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
    set((state) => ({ drafts: { ...state.drafts, [sessionId]: text } })),
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
