import { beforeEach, expect, it } from "vitest";

import { useAcp } from "@renderer/state/acp";
import { useComposer } from "@renderer/state/composer";
import { useSessions } from "@renderer/state/sessions";
import { initialSessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

/**
 * What the composer holds per session — a queue carrying Files and their base64 blocks, the draft,
 * the viewer's notes with their sketches, files waiting for the box — goes when the session's row
 * is deleted, the way the acp store's state and the explorer's tabs do. An archived row keeps it.
 */
const row = (id: string, archived = false) => ({ id, projectId: "p1", agentId: "codex", title: id, cwd: "/p1", status: "idle", archived }) as unknown as Session;

beforeEach(() => {
  useSessions.setState({ sessions: [row("s1"), row("s2")], activeId: null, ready: true });
  useComposer.setState({ drafts: {}, annotations: {}, acceptedContexts: {}, referenceLabels: {}, pendingFiles: {}, draftRoots: {}, queues: {}, sending: {}, paused: {} });
});

it("lets go of everything held for a deleted session, and keeps an archived one's", () => {
  const sketch = new File(["png"], "sketch.png", { type: "image/png" });
  for (const id of ["s1", "s2"]) {
    const composer = useComposer.getState();
    composer.enqueue(id, "look", [{ type: "image", data: "AAAA", mimeType: "image/png", uri: null }], { text: "look", annotations: [], files: [sketch] });
    composer.setDraft(id, "half a thought");
    composer.insertReference(id, { file: "a.step", selector: "", label: "A" });
    composer.acceptContext(id, `op-${id}`, [{ id: `n-${id}`, kind: "annotation", references: [], text: "here" }], { root: "/p1", focus: false });
    composer.attachFile(id, sketch);
    useComposer.setState(state => ({ paused: { ...state.paused, [id]: "error" as const }, sending: { ...state.sending, [id]: 1 } }));
  }

  useSessions.getState().receive([row("s2", true)]);

  const state = useComposer.getState();
  for (const held of [state.queues, state.drafts, state.annotations, state.pendingFiles, state.draftRoots, state.referenceLabels, state.paused, state.sending]) {
    expect(Object.keys(held)).toEqual(["s2"]);
  }
  expect(Object.values(state.acceptedContexts).map(context => context.key)).toEqual(["s2"]);
});

it("puts nothing back for a session whose row went while its queued prompt was out and was then refused", async () => {
  const bridge = window.textToCad as unknown as { sessions: object };
  const saved = bridge.sessions;
  let refuse!: (reply: { stopReason: string; refused: string }) => void;
  bridge.sessions = { ...saved, prompt: () => new Promise((resolve) => (refuse = resolve)) };
  try {
    useAcp.setState({ sessions: { s1: { ...initialSessionState("s1", "codex"), status: "idle" } }, loadErrors: {} });
    const composer = useComposer.getState();
    composer.enqueue("s1", "look", [{ type: "text", text: "look" }], { text: "look", annotations: [] });
    const drained = composer.drain("s1");
    expect(useComposer.getState().sending).toHaveProperty("s1");

    // The row is deleted while main holds the prompt; main then refuses it.
    useSessions.getState().receive([row("s2")]);
    refuse({ stopReason: "refused", refused: "Codex cannot take an image in a prompt." });
    await drained;

    const state = useComposer.getState();
    for (const held of [state.queues, state.drafts, state.paused, state.sending]) {
      expect(Object.keys(held)).toEqual([]);
    }
  } finally {
    bridge.sessions = saved;
  }
});
