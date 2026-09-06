import { observable, runInAction } from 'mobx';
import { describe, expect, it } from 'vitest';
import type { PromptLibraryPrompt } from '@core/primitives/prompt-library/api';
import { createPromptLibraryListView } from './prompt-library-list-model';

describe('createPromptLibraryListView', () => {
  it('keeps stored order and searches title and prompt body', () => {
    const view = createPromptLibraryListView({
      kind: 'sync',
      items: [
        prompt('b', 'Review checklist', 'Walk the diff for missing tests'),
        prompt('a', 'Bug triage', 'Reproduce, then bisect the regression'),
      ],
    });
    const search = (query: string) => {
      view.store.search!.setQuery(query);
      return view.store.orderedIds;
    };

    expect(search('')).toEqual(['b', 'a']);
    expect(search('checklist')).toEqual(['b']);
    expect(search('BISECT')).toEqual(['a']);
    expect(search('nothing')).toEqual([]);
  });

  it('re-derives when the observable source changes', () => {
    const box = observable.box<PromptLibraryPrompt[]>([], { deep: false });
    const view = createPromptLibraryListView({ kind: 'sync', items: () => box.get() });

    expect(view.store.orderedIds).toEqual([]);
    runInAction(() => box.set([prompt('a', 'Bug triage', 'Reproduce it')]));
    expect(view.store.orderedIds).toEqual(['a']);
  });
});

function prompt(id: string, title: string, body: string): PromptLibraryPrompt {
  return { id, title, prompt: body };
}
