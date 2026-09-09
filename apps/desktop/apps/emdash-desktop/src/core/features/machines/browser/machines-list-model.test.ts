import { observable, runInAction } from 'mobx';
import { describe, expect, it } from 'vitest';
import type { ConnectionState, SshConfig } from '@core/primitives/ssh/api';
import {
  createMachinesListView,
  MACHINES_SECTION_OTHER,
  MACHINES_SECTION_RECENT,
} from './machines-list-model';

describe('createMachinesListView', () => {
  it('sorts by name and groups into Recently used / Other by connection state', () => {
    const { view, setState } = setup([
      machine('a', 'Zeta'),
      machine('b', 'Alpha'),
      machine('c', 'Mid'),
    ]);
    setState('c', 'connected');

    expect(view.store.sections?.map((section) => section.key)).toEqual([
      MACHINES_SECTION_RECENT,
      MACHINES_SECTION_OTHER,
    ]);
    expect(view.store.sections?.[0]?.items.map((item) => item.id)).toEqual(['c']);
    expect(view.store.sections?.[1]?.items.map((item) => item.id)).toEqual(['b', 'a']);
  });

  it('re-derives sections when connection state changes', () => {
    const { view, setState } = setup([machine('a', 'Alpha')]);
    expect(view.store.sections?.map((section) => section.key)).toEqual([MACHINES_SECTION_OTHER]);

    setState('a', 'connecting');
    expect(view.store.sections?.map((section) => section.key)).toEqual([MACHINES_SECTION_RECENT]);
  });

  it('searches name, host, and username', () => {
    const { view } = setup([
      machine('a', 'Build box', 'build.example.com', 'ci'),
      machine('b', 'Dev box', 'dev.internal', 'david'),
    ]);
    const search = (query: string) => {
      view.store.search!.setQuery(query);
      return view.store.orderedIds;
    };

    expect(search('build')).toEqual(['a']);
    expect(search('dev.internal')).toEqual(['b']);
    expect(search('DAVID')).toEqual(['b']);
    expect(search('nothing')).toEqual([]);
    expect(search('')).toEqual(['a', 'b']);
  });

  it('re-derives when machines are added to the observable source', () => {
    const machines = observable.array<SshConfig>([], { deep: false });
    const view = createMachinesListView({
      getMachines: () => machines,
      isRecentlyUsed: () => false,
    });

    expect(view.store.visibleItems).toEqual([]);
    runInAction(() => machines.push(machine('a', 'Alpha')));
    expect(view.store.orderedIds).toEqual(['a']);
  });
});

function setup(initial: SshConfig[]) {
  const machines = observable.array<SshConfig>(initial, { deep: false });
  const states = observable.map<string, ConnectionState>();
  const view = createMachinesListView({
    getMachines: () => machines,
    isRecentlyUsed: (candidate) => {
      const state = states.get(candidate.id) ?? 'disconnected';
      return state === 'connected' || state === 'connecting' || state === 'reconnecting';
    },
  });
  return {
    view,
    setState: (id: string, state: ConnectionState) => runInAction(() => states.set(id, state)),
  };
}

function machine(id: string, name: string, host = 'example.com', username = 'root'): SshConfig {
  return { id, name, host, port: 22, username, authType: 'agent' };
}
