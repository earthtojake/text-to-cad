import type * as monaco from 'monaco-editor';
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import type { DraftComment } from '@core/features/source-control/api/browser/diff-view/stores/draft-comments-store';
import { MonacoCommentManager } from './monaco-comment-manager';

interface UseDiffEditorCommentsOptions {
  editor: monaco.editor.IStandaloneDiffEditor | null;
  comments: DraftComment[];
  onAddComment: (lineNumber: number, content: string, lineContent?: string) => void | Promise<void>;
  onEditComment: (id: string, content: string) => void | Promise<void>;
  onDeleteComment: (id: string) => void | Promise<void>;
}

export function useDiffEditorComments({
  editor,
  comments,
  onAddComment,
  onEditComment,
  onDeleteComment,
}: UseDiffEditorCommentsOptions): void {
  const managerRef = useRef<MonacoCommentManager | null>(null);

  const callbacks = useMemo(
    () => ({
      onAddComment,
      onEditComment,
      onDeleteComment,
    }),
    [onAddComment, onEditComment, onDeleteComment]
  );

  const commentsRef = useRef(comments);
  useLayoutEffect(() => {
    commentsRef.current = comments;
  });

  useEffect(() => {
    if (!editor) return;

    const manager = new MonacoCommentManager(editor, callbacks);
    managerRef.current = manager;
    manager.setComments(commentsRef.current);

    return () => {
      manager.dispose();
      managerRef.current = null;
    };
  }, [editor, callbacks]);

  useEffect(() => {
    managerRef.current?.setComments(comments);
  }, [comments]);
}
