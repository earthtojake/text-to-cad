import type { ExternalListSource } from '@emdash/ui/react/patterns';
import { observable, runInAction } from 'mobx';
import { describe, expect, it } from 'vitest';
import {
  AGENTS_SECTION_INSTALLED,
  AGENTS_SECTION_NOT_INSTALLED,
  AGENTS_SECTION_RECOMMENDED,
  createAgentsListView,
  type AgentListItem,
} from './agents-list-model';

const agents = [
  { id: 'opencode', name: 'OpenCode', status: 'available' },
  { id: 'codex', name: 'Codex', status: 'missing' },
  { id: 'claude', name: 'Claude', status: 'available' },
  { id: 'qwen', name: 'Qwen', status: 'missing' },
  { id: 'pi', name: 'Pi', status: 'missing' },
  { id: 'auggie', name: 'Auggie', status: 'missing' },
] satisfies AgentListItem[];

function externalSource<T extends AgentListItem>(items: () => T[]): ExternalListSource<T> {
  return { kind: 'external', items, status: () => 'idle' };
}

describe('createAgentsListView', () => {
  it('sorts by name and groups into the three fixed sections in order', () => {
    const view = createAgentsListView(externalSource(() => agents));

    expect(view.store.sections?.map((section) => section.key)).toEqual([
      AGENTS_SECTION_INSTALLED,
      AGENTS_SECTION_RECOMMENDED,
      AGENTS_SECTION_NOT_INSTALLED,
    ]);
    expect(view.store.sections?.map((section) => section.items.map((item) => item.name))).toEqual([
      ['Claude', 'OpenCode'],
      ['Codex', 'Pi'],
      ['Auggie', 'Qwen'],
    ]);
  });

  it('drops sections with no agents', () => {
    const view = createAgentsListView(
      externalSource(() => agents.filter((agent) => agent.status === 'missing'))
    );

    expect(view.store.sections?.map((section) => section.key)).toEqual([
      AGENTS_SECTION_RECOMMENDED,
      AGENTS_SECTION_NOT_INSTALLED,
    ]);
  });

  it('searches by name across every section, preserving section order', () => {
    const view = createAgentsListView(externalSource(() => agents));
    const search = (query: string) => {
      view.store.search!.setQuery(query);
      return view.store.sections?.map((section) => section.items.map((item) => item.name));
    };

    expect(search('o')).toEqual([['OpenCode'], ['Codex']]);
    expect(search('CLAUDE')).toEqual([['Claude']]);
    expect(search('nothing')).toEqual([]);
    expect(search('')).toEqual([
      ['Claude', 'OpenCode'],
      ['Codex', 'Pi'],
      ['Auggie', 'Qwen'],
    ]);
  });

  it('re-derives when the observable source changes', () => {
    const box = observable.box<AgentListItem[]>([], { deep: false });
    const view = createAgentsListView(externalSource(() => box.get()));

    expect(view.store.orderedIds).toEqual([]);
    runInAction(() => box.set([{ id: 'claude', name: 'Claude', status: 'available' }]));
    expect(view.store.orderedIds).toEqual(['claude']);
  });
});
