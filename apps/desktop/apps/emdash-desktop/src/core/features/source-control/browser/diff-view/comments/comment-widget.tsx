import { Button } from '@emdash/ui/react/primitives';
import { Check, Pencil, Trash2, X } from 'lucide-react';
import { useRef, useState } from 'react';
import type { DraftComment } from '@core/features/source-control/api/browser/diff-view/stores/draft-comments-store';
import { Comment, useTextareaAutoFocus } from './comment-card';

interface CommentWidgetProps {
  comment: DraftComment;
  onEdit: (content: string) => void | Promise<void>;
  onDelete: () => void | Promise<void>;
}

export const CommentWidget: React.FC<CommentWidgetProps> = ({ comment, onEdit, onDelete }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(comment.content);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  useTextareaAutoFocus(editTextareaRef, isEditing);

  const handleStartEditing = () => {
    setEditContent(comment.content);
    setIsEditing(true);
  };

  const handleSave = () => {
    if (editContent.trim()) {
      void onEdit(editContent.trim());
      setIsEditing(false);
      if (document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
    }
  };

  const handleCancel = () => {
    setEditContent(comment.content);
    setIsEditing(false);
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSave();
    }
    if (e.key === 'Escape') {
      handleCancel();
    }
  };

  return (
    <Comment.Root>
      <Comment.Header>
        <Comment.Title>
          {isEditing ? 'Edit comment' : 'Comment'}
          <Comment.Meta className="ml-2">(Line {comment.lineNumber})</Comment.Meta>
        </Comment.Title>
        <Comment.Actions>
          {isEditing ? (
            <>
              <Button
                variant="ghost"
                size="xs"
                icon
                className="h-8 w-8"
                onClick={handleCancel}
                title="Cancel (Esc)"
                aria-label="Cancel edit comment"
              >
                <X className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="xs"
                icon
                className="h-8 w-8"
                onClick={handleSave}
                disabled={!editContent.trim()}
                title="Save (Cmd/Ctrl+Enter)"
                aria-label="Save comment"
              >
                <Check className="h-4 w-4 text-foreground-success" />
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                size="xs"
                icon
                className="h-8 w-8"
                onClick={handleStartEditing}
                title="Edit"
                aria-label="Edit comment"
              >
                <Pencil className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="xs"
                icon
                className="h-8 w-8 text-foreground-destructive hover:text-foreground-destructive"
                onClick={() => void onDelete()}
                title="Delete"
                aria-label="Delete comment"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
        </Comment.Actions>
      </Comment.Header>

      <Comment.Body>
        {!isEditing ? (
          <Comment.Textarea
            readOnly
            value={comment.content}
            onDoubleClick={handleStartEditing}
            tabIndex={-1}
            onMouseDown={(event) => event.preventDefault()}
            onFocus={(event) => event.currentTarget.blur()}
          />
        ) : (
          <Comment.Textarea
            ref={editTextareaRef}
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Update the note..."
          />
        )}
      </Comment.Body>
    </Comment.Root>
  );
};
