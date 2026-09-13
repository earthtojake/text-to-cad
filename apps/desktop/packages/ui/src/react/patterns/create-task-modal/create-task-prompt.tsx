import { File, Image as ImageIcon, RotateCw, X } from 'lucide-react';
import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from 'react';
import { PromptEditor } from '../../components/prompt-editor/prompt-editor';
import type {
  CommandItem,
  MentionItem,
  PromptEditorRef,
} from '../../components/prompt-editor/types';
import { Button } from '../../primitives/button';
import { Spinner } from '../../primitives/spinner';
import type {
  CreateTaskPromptIntent,
  CreateTaskPromptHandle,
  CreateTaskPromptProps,
  CreateTaskPromptResource,
  CreateTaskResourceInsertion,
  CreateTaskResourceOffer,
} from './create-task-modal.types';
import * as styles from './create-task-prompt.css';

function insertionAtDocumentEnd(value: string): CreateTaskResourceInsertion {
  return { baseValue: value, range: { from: value.length, to: value.length } };
}

function snapshotTransfer(
  source: CreateTaskResourceOffer['source'],
  dataTransfer: DataTransfer,
  insertion: CreateTaskResourceInsertion
): CreateTaskResourceOffer {
  const transferData: Record<string, string> = {};
  for (const type of dataTransfer.types) {
    if (type === 'Files') continue;
    transferData[type] = dataTransfer.getData(type);
  }

  return {
    ...insertion,
    source,
    files: Array.from(dataTransfer.files),
    transferData,
    containsOrdinaryText: Boolean(transferData['text/plain']),
  };
}

export function replaceSavedPromptQuery(
  value: string,
  query: string,
  insertionText: string,
  insertionOffset: number | null
): string {
  const offsetMatches =
    insertionOffset !== null &&
    value.slice(insertionOffset, insertionOffset + query.length) === query;
  const from = offsetMatches ? insertionOffset : value.lastIndexOf(query);
  if (from < 0) return `${value}${insertionText}`;
  return `${value.slice(0, from)}${insertionText}${value.slice(from + query.length)}`;
}

function resourceMessage(resource: CreateTaskPromptResource): string | null {
  switch (resource.status.kind) {
    case 'pending':
      return resource.status.message ?? 'Preparing…';
    case 'ready':
      return resource.status.metadata;
    case 'retryable-error':
    case 'terminal-error':
      return resource.status.message;
  }
}

function ResourceActions({
  resource,
  onIntent,
}: {
  resource: CreateTaskPromptResource;
  onIntent: (intent: CreateTaskPromptIntent) => void;
}) {
  return (
    <>
      {resource.status.kind === 'retryable-error' && (
        <Button
          icon
          size="xs"
          aria-label={`Retry ${resource.name}`}
          onClick={() =>
            onIntent({
              type: 'prompt.resource-retry-requested',
              resourceId: resource.id,
            })
          }
        >
          <RotateCw />
        </Button>
      )}
      <Button
        icon
        size="xs"
        aria-label={`Remove ${resource.name}`}
        onClick={() =>
          onIntent({
            type: 'prompt.resource-remove-requested',
            resourceId: resource.id,
          })
        }
      >
        <X />
      </Button>
    </>
  );
}

export const CreateTaskPrompt = forwardRef<CreateTaskPromptHandle, CreateTaskPromptProps>(
  function CreateTaskPrompt({ state, onIntent }, ref) {
    const [dragActive, setDragActive] = useState(false);
    const editorRef = useRef<PromptEditorRef>(null);
    const disabled = state.editability.kind === 'read-only';
    const readOnlyReason =
      state.editability.kind === 'read-only' ? state.editability.reason : undefined;
    const fileResources = state.resources.filter((resource) => resource.kind === 'file');
    const fileResourceMentions: MentionItem[] = fileResources.map((resource) => ({
      id: resource.id,
      label: resource.mentionToken.replace(/^@/, ''),
      name: resource.name,
      kind: 'file',
      pending: resource.status.kind === 'pending',
      serializedText: resource.mentionToken,
    }));
    const failedFileResources = fileResources.filter(
      (resource) =>
        resource.status.kind === 'retryable-error' || resource.status.kind === 'terminal-error'
    );
    const imageResources = state.resources.filter((resource) => resource.kind === 'image');
    const getInsertion = useCallback(
      (range?: CreateTaskResourceInsertion['range']): CreateTaskResourceInsertion => ({
        baseValue: state.value,
        range:
          range ?? editorRef.current?.getSelection() ?? insertionAtDocumentEnd(state.value).range,
      }),
      [state.value]
    );
    useImperativeHandle(
      ref,
      () => ({
        focus: () => editorRef.current?.focus(),
        getInsertion: () => getInsertion(),
      }),
      [getInsertion]
    );

    const savedPrompts =
      state.savedPrompts.kind === 'ready' ||
      state.savedPrompts.kind === 'refreshing' ||
      state.savedPrompts.kind === 'stale-error'
        ? state.savedPrompts.items
        : [];
    const savedPromptCommands: CommandItem[] = savedPrompts.map((prompt) => ({
      id: prompt.id,
      name: prompt.title,
      label: prompt.title,
      description: prompt.preview,
      behavior: 'execute',
    }));

    const handleChange = useCallback(
      (value: string) => {
        const removedResourceIds = fileResources
          .filter(
            (resource) =>
              state.value.includes(resource.mentionToken) && !value.includes(resource.mentionToken)
          )
          .map((resource) => resource.id);
        onIntent({ type: 'prompt.changed', value, removedResourceIds });
      },
      [fileResources, onIntent, state.value]
    );

    return (
      <div
        className={styles.root}
        onDragEnter={(event) => {
          if (state.intake.kind === 'unavailable' || !event.dataTransfer.types.includes('Files')) {
            return;
          }
          event.preventDefault();
          setDragActive(true);
        }}
        onDragOver={(event) => {
          if (state.intake.kind === 'unavailable') return;
          event.preventDefault();
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null))
            setDragActive(false);
        }}
        onDrop={(event) => {
          setDragActive(false);
          if (state.intake.kind === 'unavailable') return;
          event.preventDefault();
          const dropPosition = editorRef.current?.getPositionAtCoordinates({
            left: event.clientX,
            top: event.clientY,
          });
          onIntent({
            type: 'prompt.resources-offered',
            offer: snapshotTransfer(
              'drop',
              event.dataTransfer,
              getInsertion(
                dropPosition === null || dropPosition === undefined
                  ? undefined
                  : { from: dropPosition, to: dropPosition }
              )
            ),
          });
        }}
        onPaste={(event) => {
          if (state.intake.kind === 'unavailable' || event.clipboardData.files.length === 0) return;
          onIntent({
            type: 'prompt.resources-offered',
            offer: snapshotTransfer('paste', event.clipboardData, getInsertion()),
          });
        }}
      >
        {dragActive && <div className={styles.dropOverlay}>Add files to this Prompt</div>}

        {failedFileResources.length > 0 && (
          <div
            className={styles.fileMentions}
            aria-label={`${failedFileResources.length} unavailable file resources`}
          >
            {failedFileResources.map((resource) => {
              const error =
                resource.status.kind === 'retryable-error' ||
                resource.status.kind === 'terminal-error';
              return (
                <span
                  key={resource.id}
                  className={styles.fileMention}
                  data-status={resource.status.kind}
                >
                  {resource.status.kind === 'pending' ? <Spinner size="sm" /> : <File />}
                  <span className={styles.resourceName}>{resource.name}</span>
                  {resourceMessage(resource) && (
                    <span className={error ? styles.resourceError : undefined}>
                      {resourceMessage(resource)}
                    </span>
                  )}
                  <ResourceActions resource={resource} onIntent={onIntent} />
                </span>
              );
            })}
          </div>
        )}

        <PromptEditor
          ref={editorRef}
          value={state.value}
          mentions={fileResourceMentions}
          className={styles.editor}
          placeholder="Describe what the agent should do, or use / to select a saved Prompt…"
          disabled={disabled}
          submitShortcut="mod-enter"
          clearOnSubmit={false}
          allowEmptySubmit
          commandPopupOpen={state.completionOpen}
          onCommandPopupOpenChange={(open) =>
            onIntent({ type: 'prompt.completion-open-changed', open })
          }
          onChange={handleChange}
          onSubmit={() => onIntent({ type: 'prompt.create-attempted' })}
          queryCommands={async (query) => {
            onIntent({ type: 'prompt.completion-query-changed', query });
            return savedPromptCommands;
          }}
          onCommand={(item) => {
            const prompt = savedPrompts.find((candidate) => candidate.id === item.id);
            if (!prompt) return;
            const query = `/${state.completionQuery}`;
            const insertionOffset = editorRef.current?.getSelection().from ?? null;
            const nextValue = replaceSavedPromptQuery(
              state.value,
              query,
              prompt.insertionText,
              insertionOffset
            );
            onIntent({
              type: 'prompt.saved-prompt-selected',
              promptId: prompt.id,
              nextValue,
            });
            onIntent({ type: 'prompt.completion-open-changed', open: false });
          }}
        />

        {state.completionOpen && state.savedPrompts.kind === 'loading' && (
          <div className={styles.completionStatus} aria-live="polite">
            <Spinner size="sm" />
            Loading saved Prompts…
          </div>
        )}
        {state.completionOpen && state.savedPrompts.kind === 'empty' && (
          <div className={styles.completionStatus}>No saved Prompts</div>
        )}
        {state.completionOpen && state.savedPrompts.kind === 'unavailable' && (
          <div className={styles.completionStatus}>{state.savedPrompts.reason}</div>
        )}
        {state.completionOpen &&
          (state.savedPrompts.kind === 'error' || state.savedPrompts.kind === 'stale-error') && (
            <div className={styles.completionStatus} role="alert">
              <span>{state.savedPrompts.message}</span>
              {state.savedPrompts.retryable && (
                <Button
                  size="xs"
                  onClick={() => onIntent({ type: 'prompt.saved-prompts-retry-requested' })}
                >
                  <RotateCw />
                  Retry
                </Button>
              )}
            </div>
          )}

        {readOnlyReason && <p className={styles.readOnlyReason}>{readOnlyReason}</p>}

        {imageResources.length > 0 && (
          <div
            className={styles.imageShelf}
            aria-label={`${imageResources.length} image attachments`}
          >
            {imageResources.map((resource) => {
              const message = resourceMessage(resource);
              return (
                <div key={resource.id} className={styles.image} data-status={resource.status.kind}>
                  {resource.previewSrc ? (
                    <button
                      type="button"
                      aria-label={`View ${resource.name}`}
                      onClick={() =>
                        onIntent({
                          type: 'prompt.image-view-requested',
                          resourceId: resource.id,
                        })
                      }
                    >
                      <img className={styles.thumbnail} src={resource.previewSrc} alt="" />
                    </button>
                  ) : (
                    <span className={styles.imagePlaceholder}>
                      {resource.status.kind === 'pending' ? <Spinner size="sm" /> : <ImageIcon />}
                    </span>
                  )}
                  <span className={styles.resourceName} title={resource.name}>
                    {resource.name}
                  </span>
                  {message && <span title={message}>{message}</span>}
                  <span className={styles.imageActions}>
                    <ResourceActions resource={resource} onIntent={onIntent} />
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }
);
