import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { cell, expose, peek, produce, type Cell } from '@emdash/wire/state';
import {
  tuiAgentsContract,
  type TuiAgentStateList,
  type TuiSessionList,
} from '#runtimes/tui-agents/api';

export type TuiSessionsListModel = { states: { list: Cell<TuiSessionList> } };
export type TuiAgentStatesListModel = { states: { list: Cell<TuiAgentStateList> } };
export type TuiSessionsLiveModel = LeasedLiveModelProvider<typeof tuiAgentsContract.sessions> & {
  model: TuiSessionsListModel;
  get(key: unknown): TuiSessionsListModel | undefined;
};
export type TuiAgentStatesLiveModel = LeasedLiveModelProvider<
  typeof tuiAgentsContract.agentStates
> & {
  model: TuiAgentStatesListModel;
  get(key: unknown): TuiAgentStatesListModel | undefined;
};

export function createTuiSessionsLiveModel(): TuiSessionsLiveModel {
  const model = { states: { list: cell({} satisfies TuiSessionList) } };
  return Object.assign(
    expose(tuiAgentsContract.sessions, { list: model.states.list }, { publish: { list: 'diff' } }),
    { model, get: () => model }
  );
}

export function createTuiAgentStatesLiveModel(): TuiAgentStatesLiveModel {
  const model = { states: { list: cell({} satisfies TuiAgentStateList) } };
  return Object.assign(
    expose(
      tuiAgentsContract.agentStates,
      { list: model.states.list },
      { publish: { list: 'diff' } }
    ),
    { model, get: () => model }
  );
}

export function createTuiSessionsListModel(liveModel: TuiSessionsLiveModel): TuiSessionsListModel {
  return liveModel.model;
}

export function createTuiAgentStatesListModel(
  liveModel: TuiAgentStatesLiveModel
): TuiAgentStatesListModel {
  return liveModel.model;
}

export function produceCell<T>(target: Cell<T>, mutator: (draft: T) => void): void {
  target.set(produce(peek(target), mutator));
}
