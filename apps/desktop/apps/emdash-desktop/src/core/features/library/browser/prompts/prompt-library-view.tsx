import {
  CollectionToolbar,
  CollectionView,
  PageLayout,
  useQueryListSource,
} from '@emdash/ui/react/patterns';
import { Button, DropdownMenu, toast } from '@emdash/ui/react/primitives';
import { EllipsisIcon, LibraryIcon, Pencil, Plus, Trash2 } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { usePromptLibrary } from '@core/features/library/api/browser/prompts/use-prompt-library';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import { useSearchFocusHotkeys } from '@core/primitives/keybindings/browser';
import type { PromptLibraryPrompt } from '@core/primitives/prompt-library/api';
import {
  createPromptLibraryListView,
  type PromptLibraryListViewModel,
} from './prompt-library-list-model';

function createPromptId() {
  return globalThis.crypto?.randomUUID?.() ?? `prompt-${Date.now()}`;
}

/** Row content (two-line text + tiered actions) — the CollectionView shell owns interaction. */
function PromptRow({
  item,
  disabled,
  onEdit,
  onDelete,
}: {
  item: PromptLibraryPrompt;
  disabled: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="group flex w-full items-center">
      <div className="min-w-0 flex-1">
        <div className="text-md truncate text-foreground">{item.title}</div>
        <div className="mt-1 line-clamp-1 text-xs leading-relaxed text-foreground-muted">
          {item.prompt}
        </div>
      </div>
      {/* Trailing actions are explicit controls — clicks must not reach the row. */}
      <div
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
        className="flex shrink-0 items-center gap-1 opacity-100 sm:opacity-0 sm:transition-opacity sm:group-focus-within:opacity-100 sm:group-hover:opacity-100"
      >
        <Button
          variant="ghost"
          size="xs"
          icon
          onClick={onEdit}
          disabled={disabled}
          aria-label={`Edit ${item.title}`}
        >
          <Pencil />
        </Button>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            render={
              <Button
                type="button"
                variant="ghost"
                size="xs"
                icon
                disabled={disabled}
                aria-label={`Actions for ${item.title}`}
              />
            }
          >
            <EllipsisIcon className="size-3.5" />
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="end">
            <DropdownMenu.Item onClick={onEdit}>
              <Pencil />
              Edit…
            </DropdownMenu.Item>
            <DropdownMenu.Separator />
            <DropdownMenu.Item variant="destructive" onClick={onDelete}>
              <Trash2 />
              Delete…
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </div>
    </div>
  );
}

export function PromptLibraryView() {
  const {
    value: promptLibrary,
    update: updatePromptLibrary,
    isLoading: isPromptLibraryLoading,
    isSaving: isPromptLibrarySaving,
  } = usePromptLibrary();
  const openPromptModal = useOpenModal('promptModal');
  const openConfirm = useOpenModal('confirmActionModal');

  const isDisabled = isPromptLibraryLoading || isPromptLibrarySaving;

  // The prompt-library hook swallows query errors (optimistic updates roll
  // back instead), so only data and loading are mirrored into the view. While
  // loading, `value` is a fresh `[]` each render — pass undefined instead so
  // the snapshot stays stable.
  const source = useQueryListSource(
    {
      data: isPromptLibraryLoading ? undefined : promptLibrary,
      isLoading: isPromptLibraryLoading,
      isError: false,
      error: null,
    },
    (rows: PromptLibraryPrompt[]) => rows
  );
  const [view] = useState(() => createPromptLibraryListView(source));

  const upsertPrompt = (prompt: PromptLibraryPrompt, successTitle: string) => {
    const exists = promptLibrary.some((item) => item.id === prompt.id);
    const nextPrompts = exists
      ? promptLibrary.map((item) => (item.id === prompt.id ? prompt : item))
      : [...promptLibrary, prompt];
    updatePromptLibrary(nextPrompts, {
      onSuccess: () => toast(successTitle),
    });
  };

  const createPrompt = () => {
    void openPromptModal().then((outcome) => {
      if (!outcome.success) return;
      upsertPrompt({ id: createPromptId(), ...outcome.data }, 'Prompt added');
    });
  };

  const editPrompt = (prompt: PromptLibraryPrompt) => {
    void openPromptModal({
      initialPrompt: prompt,
    }).then((outcome) => {
      if (!outcome.success) return;
      upsertPrompt({ ...prompt, ...outcome.data }, 'Prompt updated');
    });
  };

  const deletePrompt = (prompt: PromptLibraryPrompt) => {
    void openConfirm({
      title: 'Delete prompt?',
      description: `"${prompt.title}" will be removed from the prompt library.`,
      confirmLabel: 'Delete',
    }).then((outcome) => {
      if (!outcome.success) return;
      updatePromptLibrary(
        promptLibrary.filter((item) => item.id !== prompt.id),
        {
          onSuccess: () => toast('Prompt deleted'),
        }
      );
    });
  };

  return (
    <div className="flex min-h-0 flex-col gap-4 text-foreground">
      <PageLayout.Header
        sticky
        title="Prompts"
        description="Manage reusable prompts that can be sent from task prompt menus."
      />
      <view.Root>
        <CollectionView
          view={view}
          renderRow={(prompt) => (
            <PromptRow
              item={prompt}
              disabled={isDisabled}
              onEdit={() => editPrompt(prompt)}
              onDelete={() => deletePrompt(prompt)}
            />
          )}
          toolbar={<PromptsToolbar view={view} onNewPrompt={createPrompt} disabled={isDisabled} />}
          onItemClick={(prompt) => {
            if (!isDisabled) editPrompt(prompt);
          }}
          emptySlot={<PromptsEmptyState hasPrompts={promptLibrary.length > 0} />}
        />
      </view.Root>
    </div>
  );
}

const PromptsToolbar = observer(function PromptsToolbar({
  view,
  onNewPrompt,
  disabled,
}: {
  view: PromptLibraryListViewModel;
  onNewPrompt: () => void;
  disabled: boolean;
}) {
  const search = view.useSearch();
  const searchRef = useSearchFocusHotkeys();
  return (
    <CollectionToolbar
      ref={searchRef}
      searchValue={search.query}
      onSearchValueChange={search.setQuery}
      searchPlaceholder="Search prompts…"
      actions={
        <Button variant="primary" onClick={onNewPrompt} disabled={disabled} aria-label="New Prompt">
          <Plus className="size-4" />
          <span className="[@container(max-width:520px)]:hidden">New Prompt</span>
        </Button>
      }
    />
  );
});

// Icon-bearing empty state — `EmptyState` has no icon slot, so this stays
// custom under the rich-states carve-out.
function PromptsEmptyState({ hasPrompts }: { hasPrompts: boolean }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center p-8 text-center">
      <LibraryIcon className="mb-3 size-8 text-foreground-passive" />
      <div className="text-sm text-foreground">
        {hasPrompts ? 'No prompts match your search' : 'No prompts'}
      </div>
      <p className="mt-1 max-w-sm text-xs text-foreground-passive">
        {hasPrompts
          ? 'Try a different title or prompt text.'
          : 'Add a prompt to reuse it from task prompt menus.'}
      </p>
    </div>
  );
}
