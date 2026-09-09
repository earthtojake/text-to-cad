import { createListView, createTextMatcher, type ListSource } from '@emdash/ui/react/patterns';
import type { PromptLibraryPrompt } from '@core/primitives/prompt-library/api';

/**
 * The list-view state layer for the prompt library: an externally owned source
 * (the component bridges its query via `useQueryListSource`) plus immediate
 * client-side search over the title and the prompt body. Items keep the
 * library's stored order.
 */
export function createPromptLibraryListView(source: ListSource<PromptLibraryPrompt>) {
  return createListView({
    getItemId: (prompt: PromptLibraryPrompt) => prompt.id,
    source,
    search: {
      kind: 'sync',
      predicate: createTextMatcher((prompt: PromptLibraryPrompt) => [prompt.title, prompt.prompt]),
    },
  });
}

export type PromptLibraryListViewModel = ReturnType<typeof createPromptLibraryListView>;
