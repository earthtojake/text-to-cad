import { Button } from '@emdash/ui/react/primitives';
import { Check, X } from 'lucide-react';
import { useRef, useState } from 'react';
import { Comment, useTextareaAutoFocus } from './comment-card';

interface CommentInputProps {
  lineNumber: number;
  existingContent?: string;
  onSubmit: (content: string) => void | Promise<void>;
  onCancel: () => void;
}

export const CommentInput: React.FC<CommentInputProps> = ({
  lineNumber,
  existingContent,
  onSubmit,
  onCancel,
}) => {
  const [content, setContent] = useState(existingContent || '');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useTextareaAutoFocus(textareaRef, true);

  const handleSubmit = () => {
    if (content.trim()) {
      void onSubmit(content.trim());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
    if (e.key === 'Escape') {
      onCancel();
    }
  };

  return (
    <Comment.Root>
      <Comment.Header>
        <Comment.Title>
          {existingContent ? 'Edit comment' : 'Add comment'}
          <Comment.Meta className="ml-2">(Line {lineNumber})</Comment.Meta>
        </Comment.Title>
        <Comment.Actions>
          <Button
            variant="ghost"
            size="xs"
            icon
            className="h-8 w-8"
            onClick={onCancel}
            title="Cancel (Esc)"
            aria-label="Cancel comment"
          >
            <X className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="xs"
            icon
            className="h-8 w-8"
            onClick={handleSubmit}
            disabled={!content.trim()}
            title="Submit (Cmd/Ctrl+Enter)"
            aria-label="Submit comment"
          >
            <Check className="h-4 w-4 text-foreground-success" />
          </Button>
        </Comment.Actions>
      </Comment.Header>

      <Comment.Body>
        <Comment.Textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a note about this line..."
          autoFocus
        />
      </Comment.Body>
    </Comment.Root>
  );
};
