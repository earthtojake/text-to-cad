import { Button } from '@react/primitives/button';
import { cx } from '@styles/utilities/cx';
import { ArrowUp, Check, GripVertical, Trash2, X } from 'lucide-react';
import * as React from 'react';
import * as styles from './queued-prompts-band.css';

export type ComposerQueuedPrompt = {
  id: string;
  text: string;
};

export interface QueuedPromptsBandProps {
  prompts: ComposerQueuedPrompt[];
  onEdit: (id: string, text: string) => void;
  onDelete: (id: string) => void;
  onReorder: (ids: string[]) => void;
  onSendNow: (id: string) => void;
  connectToBandBelow?: boolean;
  className?: string;
}

export function QueuedPromptsBand({
  prompts,
  onEdit,
  onDelete,
  onReorder,
  onSendNow,
  connectToBandBelow = false,
  className,
}: QueuedPromptsBandProps) {
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState('');
  const [draggingId, setDraggingId] = React.useState<string | null>(null);
  const [dragOverId, setDragOverId] = React.useState<string | null>(null);
  const editInputRef = React.useRef<HTMLTextAreaElement | null>(null);

  React.useEffect(() => {
    if (!editingId) return;
    if (prompts.some((prompt) => prompt.id === editingId)) return;
    setEditingId(null);
    setDraft('');
  }, [editingId, prompts]);

  React.useEffect(() => {
    if (!editingId) return;
    editInputRef.current?.focus();
    editInputRef.current?.select();
  }, [editingId]);

  const ids = prompts.map((prompt) => prompt.id);

  const beginEdit = (prompt: ComposerQueuedPrompt) => {
    setEditingId(prompt.id);
    setDraft(prompt.text);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setDraft('');
  };

  const saveEdit = (id: string) => {
    const next = draft.trim();
    if (!next) return;
    onEdit(id, draft);
    cancelEdit();
  };

  const reorder = (fromId: string, toId: string) => {
    if (fromId === toId) return;
    const index = ids.indexOf(fromId);
    const nextIndex = ids.indexOf(toId);
    if (index < 0 || nextIndex < 0) return;
    const next = [...ids];
    const [moved] = next.splice(index, 1);
    next.splice(nextIndex, 0, moved);
    onReorder(next);
  };

  const handleDragStart = (event: React.DragEvent<HTMLButtonElement>, id: string) => {
    setDraggingId(id);
    setDragOverId(null);
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', id);
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>, id: string) => {
    if (!draggingId) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    setDragOverId(id);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>, id: string) => {
    event.preventDefault();
    const draggedId = event.dataTransfer.getData('text/plain') || draggingId;
    if (draggedId) reorder(draggedId, id);
    setDraggingId(null);
    setDragOverId(null);
  };

  const handleDragEnd = () => {
    setDraggingId(null);
    setDragOverId(null);
  };

  if (prompts.length === 0) return null;

  return (
    <div className={cx(styles.band, connectToBandBelow && styles.bandConnectedBelow, className)}>
      <div className={styles.header}>
        <span>
          <span className={styles.headerStrong}>Queued prompts</span> ({prompts.length})
        </span>
      </div>

      <div className={styles.list}>
        {prompts.map((prompt, index) => {
          const isEditing = editingId === prompt.id;
          return (
            <div
              key={prompt.id}
              className={styles.row}
              data-dragging={draggingId === prompt.id || undefined}
              data-drag-over={dragOverId === prompt.id || undefined}
              onDragOver={(event) => handleDragOver(event, prompt.id)}
              onDragLeave={() =>
                setDragOverId((current) => (current === prompt.id ? null : current))
              }
              onDrop={(event) => handleDrop(event, prompt.id)}
            >
              <span className={styles.indexSlot}>
                <span className={styles.indexNumber}>{index + 1}</span>
                {!isEditing && (
                  <button
                    type="button"
                    className={styles.dragHandle}
                    draggable
                    aria-label={`Reorder queued prompt ${index + 1}`}
                    title="Drag to reorder"
                    onClick={(event) => event.stopPropagation()}
                    onDragStart={(event) => handleDragStart(event, prompt.id)}
                    onDragEnd={handleDragEnd}
                  >
                    <GripVertical className={styles.dragHandleIcon} aria-hidden />
                  </button>
                )}
              </span>

              {isEditing ? (
                <div className={styles.editArea}>
                  <textarea
                    ref={editInputRef}
                    className={styles.editInput}
                    value={draft}
                    rows={2}
                    aria-label={`Edit queued prompt ${index + 1}`}
                    onChange={(event) => setDraft(event.currentTarget.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Escape') {
                        event.preventDefault();
                        cancelEdit();
                      }
                      if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        saveEdit(prompt.id);
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    icon
                    aria-label="Save queued prompt"
                    title="Save queued prompt"
                    disabled={!draft.trim()}
                    onClick={() => saveEdit(prompt.id)}
                  >
                    <Check />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    icon
                    aria-label="Cancel edit"
                    title="Cancel edit"
                    onClick={cancelEdit}
                  >
                    <X />
                  </Button>
                </div>
              ) : (
                <button
                  type="button"
                  className={cx(styles.promptText, !prompt.text.trim() && styles.emptyText)}
                  onClick={() => beginEdit(prompt)}
                  aria-label={`Edit queued prompt ${index + 1}`}
                  title="Edit queued prompt"
                >
                  {prompt.text.trim() || 'Image-only prompt'}
                </button>
              )}

              {!isEditing && (
                <div className={styles.actions}>
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    icon
                    aria-label="Send queued prompt now"
                    title="Send now - cancels the active turn"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSendNow(prompt.id);
                    }}
                  >
                    <ArrowUp />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    tone="destructive"
                    size="xs"
                    icon
                    aria-label="Delete queued prompt"
                    title="Delete queued prompt"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDelete(prompt.id);
                    }}
                  >
                    <Trash2 />
                  </Button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
