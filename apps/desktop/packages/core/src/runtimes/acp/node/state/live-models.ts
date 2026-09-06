import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { cell, expose, peek, type Cell, produce, publishStructural } from '@emdash/wire/state';
import {
  acpApiContract,
  initialSessionConfigState,
  type AgentState,
  type PlanState,
  type PromptDraft,
  type SessionConfigState,
  type SessionMcpServer,
  type SessionState,
  type SessionSummary,
  type SessionUsage,
  type TerminalState,
  type TranscriptTurn,
} from '#runtimes/acp/api';

export type SessionLiveModels = {
  states: {
    state: Cell<SessionState>;
    config: Cell<SessionConfigState>;
    usage: Cell<SessionUsage | null>;
    plan: Cell<PlanState | null>;
    agents: Cell<AgentState[]>;
    activeTurn: Cell<TranscriptTurn | null>;
    draft: Cell<PromptDraft | null>;
    terminals: Cell<TerminalState[]>;
    mcpServers: Cell<SessionMcpServer[]>;
  };
} & { dispose(): void };
export type SessionsListModel = {
  states: {
    list: Cell<Record<string, SessionSummary>>;
  };
};
export type AcpSessionLiveHost = LeasedLiveModelProvider<typeof acpApiContract.session> & {
  models: Map<string, SessionLiveModels>;
};
export type AcpSessionsLiveHost = LeasedLiveModelProvider<typeof acpApiContract.sessions> & {
  model: SessionsListModel;
  get(key: unknown): SessionsListModel | undefined;
};

export function createAcpSessionLiveHost(): AcpSessionLiveHost {
  const models = new Map<string, SessionLiveModels>();
  return Object.assign(
    expose(
      acpApiContract.session,
      {
        state: (key) => requireSessionModel(models, key.conversationId).states.state,
        config: (key) => requireSessionModel(models, key.conversationId).states.config,
        usage: (key) => requireSessionModel(models, key.conversationId).states.usage,
        plan: (key) => requireSessionModel(models, key.conversationId).states.plan,
        agents: (key) => requireSessionModel(models, key.conversationId).states.agents,
        activeTurn: (key) => requireSessionModel(models, key.conversationId).states.activeTurn,
        draft: (key) => requireSessionModel(models, key.conversationId).states.draft,
        terminals: (key) => requireSessionModel(models, key.conversationId).states.terminals,
        mcpServers: (key) => requireSessionModel(models, key.conversationId).states.mcpServers,
      },
      { publish: 'diff' }
    ),
    { models }
  );
}

export function createAcpSessionsLiveHost(): AcpSessionsLiveHost {
  const model = { states: { list: cell<Record<string, SessionSummary>>({}) } };
  return Object.assign(
    expose(
      acpApiContract.sessions,
      {
        list: model.states.list,
      },
      { publish: { list: 'diff' } }
    ),
    { model, get: () => model }
  );
}

/**
 * Returns the live-model slot for a conversation, creating it on first use.
 *
 * The slot (and every cell in it) is stable for the life of the host. Renderer
 * replicas and the leased provider resolve a conversation's cells once and keep
 * using them across an evict-and-restart (Stop, process death, resume), so a
 * restart must publish into the cells they already hold rather than register a
 * fresh set behind the same key. A restart therefore reuses the slot and resets
 * it to the initial shape; `dispose` leaves the slot registered.
 */
export function createSessionLiveModels(
  host: AcpSessionLiveHost,
  conversationId: string,
  initialState: SessionState
): SessionLiveModels {
  const existing = host.models.get(conversationId);
  if (existing) {
    resetSessionLiveModels(existing, initialState);
    return existing;
  }
  const model: SessionLiveModels = {
    states: {
      state: cell(initialState),
      config: cell(initialSessionConfigState),
      usage: cell<SessionUsage | null>(null),
      plan: cell<PlanState | null>(null),
      agents: cell<AgentState[]>([]),
      activeTurn: cell<TranscriptTurn | null>(null),
      draft: cell<PromptDraft | null>(null),
      terminals: cell<TerminalState[]>([]),
      mcpServers: cell<SessionMcpServer[]>([]),
    },
    dispose() {
      // Keep the slot: subscribers still hold these cells, and the next start
      // for this conversation publishes into them (see above).
    },
  };
  host.models.set(conversationId, model);
  return model;
}

function resetSessionLiveModels(model: SessionLiveModels, initialState: SessionState): void {
  const { states } = model;
  publishLiveModelState(states.state, initialState, peek(states.state));
  publishLiveModelState(states.config, initialSessionConfigState, peek(states.config));
  publishLiveModelState(states.usage, null, peek(states.usage));
  publishLiveModelState(states.plan, null, peek(states.plan));
  publishLiveModelState(states.agents, [], peek(states.agents));
  publishLiveModelState(states.activeTurn, null, peek(states.activeTurn));
  publishLiveModelState(states.draft, null, peek(states.draft));
  publishLiveModelState(states.terminals, [], peek(states.terminals));
  publishLiveModelState(states.mcpServers, [], peek(states.mcpServers));
}

export function createSessionsListModel(host: AcpSessionsLiveHost): SessionsListModel {
  return host.model;
}

export function publishLiveModelState<T>(model: Cell<T>, next: T, previous: T | undefined): void {
  if (Object.is(previous, next)) return;
  publishStructural(model, next);
}

export function produceCell<T>(target: Cell<T>, mutator: (draft: T) => void): void {
  target.set(produce(peek(target), mutator));
}

export type {
  AgentState,
  PlanState,
  PromptDraft,
  SessionConfigState,
  SessionMcpServer,
  SessionState,
  SessionSummary,
  SessionUsage,
  TerminalState,
  TranscriptTurn,
};

function requireSessionModel(
  models: Map<string, SessionLiveModels>,
  conversationId: string
): SessionLiveModels {
  const model = models.get(conversationId);
  if (!model) throw new Error(`ACP session live model is not registered: ${conversationId}`);
  return model;
}
