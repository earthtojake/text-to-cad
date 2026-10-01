import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useAcp } from "@renderer/state/acp";
import { subscribeToMain } from "@renderer/state/bridge";
import { useComposer } from "@renderer/state/composer";
import type { PromptBlock } from "@shared/acp/types";
import { initialSessionState } from "@shared/acp/types";

/**
 * Main as the queue sees it: `sessions.prompt` is a reply that arrives when the turn is over,
 * and the turn's events arrive on `session.update` — `prompt/end` BEFORE that reply.
 */
const SESSION = "s1";
type Handler = (payload: unknown) => void;
let handlers: Record<string, Handler>;
let replies: { text: string; resolve: () => void; reject: (error: Error) => void }[];
let detach: () => void;
const bridge = window.textToCad as unknown as Record<string, unknown>;
const saved = { on: bridge.on, sessions: bridge.sessions };

const block = (text: string): PromptBlock[] => [{ type: "text", text }];
const emit = (event: Record<string, unknown>) =>
  handlers["session.update"]!({ sessionId: SESSION, event: { at: Date.now(), ...event } });
const start = (text: string) => emit({ type: "prompt/start", turnId: text, content: block(text) });
const end = () => emit({ type: "prompt/end", stopReason: "end_turn", usage: null });
const settle = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };
/** What main has been handed and not yet answered: more than one is two turns at once. */
const inFlight = () => replies.map(reply => reply.text);

beforeEach(() => {
  handlers = {};
  replies = [];
  bridge.on = vi.fn((channel: string, handler: Handler) => { handlers[channel] = handler; return () => {}; });
  bridge.sessions = {
    ...(saved.sessions as object),
    prompt: vi.fn(({ content }: { content: PromptBlock[] }) => new Promise((resolve, reject) => {
      const text = content[0]?.type === "text" ? content[0].text : "";
      const reply = {
        text,
        resolve: () => { replies = replies.filter(item => item !== reply); resolve({ stopReason: "end_turn" }); },
        reject: (error: Error) => { replies = replies.filter(item => item !== reply); reject(error); },
      };
      replies.push(reply);
    })),
  };
  useAcp.setState({ sessions: { [SESSION]: initialSessionState(SESSION, "claude") }, reconnecting: {} });
  useComposer.setState({ queues: {}, sending: {}, paused: {}, drafts: {}, annotations: {}, referenceLabels: {}, draftRoots: {} });
  detach = subscribeToMain();
});

afterEach(() => {
  detach();
  bridge.on = saved.on;
  bridge.sessions = saved.sessions;
});

it("sends queued prompts one at a time: prompt/end then the reply does not send two", async () => {
  const composer = useComposer.getState();
  void composer.submit(SESSION, "first", block("first"));
  // Submitted before main has said the first one started: already in flight, so queued.
  void composer.submit(SESSION, "second", block("second"));
  start("first");
  void composer.submit(SESSION, "third", block("third"));
  await settle();
  expect(inFlight()).toEqual(["first"]);
  expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["second", "third"]);

  // Main broadcasts the end, then replies to the first prompt.
  end();
  await settle();
  replies.find(reply => reply.text === "first")!.resolve();
  await settle();
  expect(inFlight(), "only the next queued prompt goes out").toEqual(["second"]);
  expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["third"]);

  start("second");
  end();
  await settle();
  replies[0]!.resolve();
  await settle();
  expect(inFlight()).toEqual(["third"]);
  expect(useComposer.getState().queues[SESSION]).toEqual([]);
});

it("a failed turn pauses the queue; what is sent next goes first and the queue resumes after it", async () => {
  const composer = useComposer.getState();
  void composer.submit(SESSION, "first", block("first"));
  start("first");
  void composer.submit(SESSION, "queued", block("queued"));
  emit({ type: "prompt/error", message: "boom" });
  replies[0]!.reject(new Error("boom"));
  await settle();
  expect(useAcp.getState().sessions[SESSION]?.status).toBe("error");
  expect(inFlight(), "nothing is sent into the failure").toEqual([]);
  expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["queued"]);

  void composer.submit(SESSION, "first", block("first"));
  await settle();
  expect(inFlight(), "the Retry goes out ahead of the queue").toEqual(["first"]);
  start("first");
  end();
  await settle();
  replies[0]!.resolve();
  await settle();
  expect(inFlight()).toEqual(["queued"]);
});

it("a prompt the IPC refuses before any turn event frees the session", async () => {
  void useComposer.getState().submit(SESSION, "first", block("first"));
  expect(useComposer.getState().sending[SESSION]).toBeDefined();
  replies[0]!.reject(new Error("no such session"));
  await settle();
  expect(useComposer.getState().sending[SESSION]).toBeUndefined();
});

it("a queue left behind by a disconnect drains when a reconnect's session.state says idle", async () => {
  const composer = useComposer.getState();
  void composer.submit(SESSION, "first", block("first"));
  start("first");
  void composer.submit(SESSION, "queued", block("queued"));
  await settle();
  // The agent is evicted mid-turn: no prompt/end, the reply rejects, the session reads closed.
  emit({ type: "status", status: "closed", error: null });
  replies[0]!.reject(new Error("disconnected"));
  await settle();
  expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["queued"]);

  // The reconnect: a full snapshot, idle, and no turn event at all.
  handlers["session.state"]!({ sessionId: SESSION, state: { ...initialSessionState(SESSION, "claude"), status: "idle" } });
  await settle();
  expect(inFlight(), "the queued prompt goes out on reconnect").toEqual(["queued"]);
  expect(useComposer.getState().queues[SESSION]).toEqual([]);
});

it("a prompt typed behind a queue while the agent is gone waits its turn: the reconnect sends the queue first", async () => {
  // The load answers once the reconnect's snapshot is in.
  let reconnected!: () => void;
  const ensureLoaded = vi.fn(() => new Promise<void>(resolve => { reconnected = resolve; }));
  const savedEnsure = useAcp.getState().ensureLoaded;
  useAcp.setState({ ensureLoaded });
  try {
    const composer = useComposer.getState();
    void composer.submit(SESSION, "A", block("A"));
    start("A");
    void composer.submit(SESSION, "B", block("B"));
    await settle();
    // Disconnected mid-turn: A's turn never ends, the session reads closed, B is left queued.
    emit({ type: "status", status: "closed", error: null });
    replies[0]!.reject(new Error("disconnected"));
    await settle();
    expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["B"]);

    void composer.submit(SESSION, "C", block("C"));
    await settle();
    expect(inFlight(), "C is not sent past the queue").toEqual([]);
    expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["B", "C"]);
    expect(ensureLoaded, "and the agent is asked back").toHaveBeenCalledWith(SESSION);

    handlers["session.state"]!({ sessionId: SESSION, state: { ...initialSessionState(SESSION, "claude"), status: "idle" } });
    reconnected();
    await settle();
    expect(inFlight()).toEqual(["B"]);
    start("B");
    end();
    await settle();
    replies[0]!.resolve();
    await settle();
    expect(inFlight()).toEqual(["C"]);
  } finally {
    useAcp.setState({ ensureLoaded: savedEnsure });
  }
});

it("on a session main is still connecting, a prompt behind a queue is queued and nothing is sent", async () => {
  // Main drives the connect, so there is no renderer load: ensureLoaded answers at once.
  const ensureLoaded = vi.fn(async () => undefined);
  const savedEnsure = useAcp.getState().ensureLoaded;
  useAcp.setState({ ensureLoaded, loading: {} });
  try {
    useComposer.getState().enqueue(SESSION, "stranded", block("stranded"));
    useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "connecting" } } });
    void useComposer.getState().submit(SESSION, "new-connecting", block("new-connecting"));
    await settle();
    expect(inFlight()).toEqual([]);
    expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["stranded", "new-connecting"]);
    expect(ensureLoaded).toHaveBeenCalledWith(SESSION);
  } finally {
    useAcp.setState({ ensureLoaded: savedEnsure });
  }
});

it("a reconnect that paints a live, busy snapshot does not have the queue's head pushed into it", async () => {
  const savedEnsure = useAcp.getState().ensureLoaded;
  for (const status of ["running", "waiting"] as const) {
    const ensureLoaded = vi.fn(async () => {
      useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status } } });
    });
    useAcp.setState({ ensureLoaded, loading: {}, sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "closed" } } });
    useComposer.setState({ queues: {}, sending: {} });
    replies = [];
    try {
      useComposer.getState().enqueue(SESSION, "stranded", block("stranded"));
      void useComposer.getState().submit(SESSION, "new", block("new"));
      await settle();
      expect(inFlight(), status).toEqual([]);
      expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["stranded", "new"]);
    } finally {
      useAcp.setState({ ensureLoaded: savedEnsure });
    }
  }
});

it("with no session state and a load still on its way, a prompt behind a queue waits", async () => {
  const ensureLoaded = vi.fn(() => new Promise<void>(() => {}));
  const savedEnsure = useAcp.getState().ensureLoaded;
  useAcp.setState({ ensureLoaded, sessions: {} });
  try {
    useComposer.getState().enqueue(SESSION, "stranded", block("stranded"));
    void useComposer.getState().submit(SESSION, "new-none", block("new-none"));
    await settle();
    expect(inFlight()).toEqual([]);
    expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["stranded", "new-none"]);
  } finally {
    useAcp.setState({ ensureLoaded: savedEnsure });
  }
});

it("a paused queue is unpaused when it is cleared or emptied, and Resume sends its head", async () => {
  const composer = useComposer.getState();
  const pause = () => {
    void composer.submit(SESSION, "failed", block("failed"));
    start("failed");
    void composer.submit(SESSION, "A", block("A"));
    emit({ type: "prompt/error", message: "boom" });
    replies[0]!.reject(new Error("boom"));
  };
  pause();
  await settle();
  expect(useComposer.getState().paused[SESSION]).toBe(true);
  composer.clearQueue(SESSION);
  expect(useComposer.getState().paused[SESSION], "cleared").toBeUndefined();

  useAcp.setState({ sessions: { [SESSION]: initialSessionState(SESSION, "claude") } });
  pause();
  await settle();
  expect(useComposer.getState().paused[SESSION]).toBe(true);
  const [only] = useComposer.getState().queues[SESSION]!;
  composer.dequeue(SESSION, only!.id);
  expect(useComposer.getState().paused[SESSION], "emptied").toBeUndefined();

  useAcp.setState({ sessions: { [SESSION]: initialSessionState(SESSION, "claude") } });
  pause();
  await settle();
  // A Retry refused before main dispatched anything: no prompt/start, still paused.
  void composer.submit(SESSION, "failed", block("failed"));
  replies[0]!.reject(new Error("refused"));
  await settle();
  expect(useComposer.getState().paused[SESSION]).toBe(true);
  useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "idle" } } });
  void composer.resume(SESSION);
  await settle();
  expect(useComposer.getState().paused[SESSION]).toBeUndefined();
  expect(inFlight()).toEqual(["A"]);
});

it("a failed turn stays paused through an eviction: the Retry goes first, then the queue in order", async () => {
  const ensureLoaded = vi.fn(async () => undefined);
  const savedEnsure = useAcp.getState().ensureLoaded;
  useAcp.setState({ ensureLoaded });
  try {
    const composer = useComposer.getState();
    void composer.submit(SESSION, "failed", block("failed"));
    start("failed");
    void composer.submit(SESSION, "A", block("A"));
    void composer.submit(SESSION, "B", block("B"));
    emit({ type: "prompt/error", message: "boom" });
    replies[0]!.reject(new Error("boom"));
    await settle();
    // The keep-alive evicts the failed session, and a reconnect comes back idle.
    emit({ type: "status", status: "closed", error: null });
    await settle();
    handlers["session.state"]!({ sessionId: SESSION, state: { ...initialSessionState(SESSION, "claude"), status: "idle" } });
    await settle();
    expect(inFlight(), "the reconnect does not resume a paused queue").toEqual([]);
    emit({ type: "status", status: "closed", error: null });
    await settle();

    void composer.submit(SESSION, "failed", block("failed"));
    await settle();
    expect(inFlight(), "the Retry goes out ahead of the queue").toEqual(["failed"]);
    expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["A", "B"]);
    handlers["session.state"]!({ sessionId: SESSION, state: { ...initialSessionState(SESSION, "claude"), status: "idle" } });
    start("failed");
    end();
    await settle();
    replies[0]!.resolve();
    await settle();
    expect(inFlight()).toEqual(["A"]);
    start("A");
    end();
    await settle();
    replies[0]!.resolve();
    await settle();
    expect(inFlight()).toEqual(["B"]);
  } finally {
    useAcp.setState({ ensureLoaded: savedEnsure });
  }
});

it("when the agent does not come back, the queue's head is sent so it fails where it can be retried", async () => {
  const ensureLoaded = vi.fn(async () => undefined);
  const savedEnsure = useAcp.getState().ensureLoaded;
  useAcp.setState({ ensureLoaded });
  try {
    useComposer.getState().enqueue(SESSION, "A", block("A"));
    useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "closed" } }, loading: {} });
    void useComposer.getState().submit(SESSION, "C", block("C"));
    await settle();
    // The load failed: still closed, nothing loading. A goes out and fails visibly; C waits behind it.
    expect(ensureLoaded).toHaveBeenCalledWith(SESSION);
    expect(inFlight()).toEqual(["A"]);
    expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["C"]);
  } finally {
    useAcp.setState({ ensureLoaded: savedEnsure });
  }
});

it("while a load is still in flight, the queue waits for its snapshot", async () => {
  const ensureLoaded = vi.fn(async () => undefined);
  const savedEnsure = useAcp.getState().ensureLoaded;
  useAcp.setState({ ensureLoaded });
  try {
    useComposer.getState().enqueue(SESSION, "A", block("A"));
    useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "connecting" } }, loading: { [SESSION]: true } });
    void useComposer.getState().submit(SESSION, "C", block("C"));
    await settle();
    expect(inFlight()).toEqual([]);
    expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["A", "C"]);
  } finally {
    useAcp.setState({ ensureLoaded: savedEnsure, loading: {} });
  }
});

it("Resume whose prompt main refuses before any turn begins keeps the queue whole, paused, and says why", async () => {
  const savedEnsure = useAcp.getState().ensureLoaded;
  useAcp.setState({ ensureLoaded: vi.fn(async () => undefined), loadErrors: {} });
  try {
    const composer = useComposer.getState();
    composer.enqueue(SESSION, "A", block("A"));
    composer.enqueue(SESSION, "B", block("B"));
    useComposer.setState({ paused: { [SESSION]: true } });
    useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "error" } } });

    void composer.resume(SESSION);
    await settle();
    expect(inFlight()).toEqual(["A"]);
    // The reload behind the prompt fails (agent not installed): no prompt/start, no prompt/error.
    replies[0]!.reject(new Error("The claude agent is not installed"));
    await settle();

    const state = useComposer.getState();
    expect(state.queues[SESSION]?.map(item => item.text), "A is back at the head").toEqual(["A", "B"]);
    expect(state.paused[SESSION]).toBe(true);
    expect(state.sending[SESSION]).toBeUndefined();
    expect(useAcp.getState().loadErrors[SESSION], "shown where a failed reconnect is").toMatch(/not installed/);

    // Once the agent is back, Resume sends A and the refusal shown is cleared when its turn starts.
    useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "idle" } } });
    void composer.resume(SESSION);
    await settle();
    expect(inFlight()).toEqual(["A"]);
    start("A");
    expect(useAcp.getState().loadErrors[SESSION]).toBeUndefined();
    expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["B"]);
  } finally {
    useAcp.setState({ ensureLoaded: savedEnsure, loadErrors: {} });
  }
});

it("a prompt main refuses after its turn began is the transcript's to show, not put back", async () => {
  useAcp.setState({ loadErrors: {} });
  void useComposer.getState().submit(SESSION, "C", block("C"));
  start("C");
  emit({ type: "prompt/error", message: "boom" });
  replies[0]!.reject(new Error("boom"));
  await settle();
  expect(useComposer.getState().queues[SESSION] ?? []).toEqual([]);
  expect(useAcp.getState().loadErrors[SESSION]).toBeUndefined();
});

it("drains the queue when a permission asked outside any turn is answered", async () => {
  useAcp.setState({ sessions: { [SESSION]: { ...initialSessionState(SESSION, "claude"), status: "idle" } } });
  emit({
    type: "permission/request",
    request: { requestId: "perm-1", acpSessionId: "", toolCallId: "c1", title: null, description: null, kind: null, input: null, options: [] },
  });
  expect(useAcp.getState().sessions[SESSION]?.status).toBe("waiting");
  void useComposer.getState().submit(SESSION, "after", block("after"));
  await settle();
  expect(inFlight(), "queued behind the waiting session").toEqual([]);
  expect(useComposer.getState().queues[SESSION]?.map(item => item.text)).toEqual(["after"]);

  // No `prompt/end` follows: the answer alone returns the session to idle.
  emit({ type: "permission/resolve", requestId: "perm-1", outcome: { state: "selected", optionId: "x" } });
  await settle();
  expect(inFlight()).toEqual(["after"]);
});
