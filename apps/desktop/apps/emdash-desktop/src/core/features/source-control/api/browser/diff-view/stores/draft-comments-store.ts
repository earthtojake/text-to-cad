import { makeAutoObservable } from 'mobx';
import {
  formatCommentsForAgent,
  getDraftCommentTargetKey,
  getDraftCommentTargetPath,
  type DraftCommentTarget,
} from '@core/primitives/line-comments/api';

const MAX_COMMENTS_PER_TASK = 200;

export type DraftComment = {
  id: string;
  taskId: string;
  filePath: string;
  target: DraftCommentTarget;
  targetKey: string;
  lineNumber: number;
  lineContent?: string | null;
  content: string;
  createdAt: string;
  updatedAt: string;
};

type CreateDraftCommentInput = {
  target: DraftCommentTarget;
  lineNumber: number;
  lineContent?: string | null;
  content: string;
};

function byCreatedAtThenLine(a: DraftComment, b: DraftComment): number {
  const byCreatedAt = a.createdAt.localeCompare(b.createdAt);
  if (byCreatedAt !== 0) return byCreatedAt;
  return a.lineNumber - b.lineNumber;
}

export class DraftCommentsStore {
  readonly commentsById = new Map<string, DraftComment>();

  constructor(readonly taskId: string) {
    makeAutoObservable(this, { getCommentsForTarget: false }, { autoBind: true });
  }

  get comments(): DraftComment[] {
    return Array.from(this.commentsById.values()).sort(byCreatedAtThenLine);
  }

  get count(): number {
    return this.commentsById.size;
  }

  get formattedForAgent(): string {
    return formatCommentsForAgent(this.comments, { includeIntro: false });
  }

  getCommentsForTarget(targetKey: string): DraftComment[] {
    return this.comments
      .filter((comment) => comment.targetKey === targetKey)
      .sort((a, b) => a.lineNumber - b.lineNumber || a.createdAt.localeCompare(b.createdAt));
  }

  addComment(input: CreateDraftCommentInput): string {
    if (this.commentsById.size >= MAX_COMMENTS_PER_TASK) {
      console.warn(
        `DraftCommentsStore: reached ${MAX_COMMENTS_PER_TASK} comment limit for task ${this.taskId}`
      );
      return crypto.randomUUID();
    }

    const now = new Date().toISOString();
    const id = crypto.randomUUID();
    const filePath = getDraftCommentTargetPath(input.target);
    const targetKey = getDraftCommentTargetKey(input.target);

    this.commentsById.set(id, {
      id,
      taskId: this.taskId,
      filePath,
      target: input.target,
      targetKey,
      lineNumber: input.lineNumber,
      lineContent: input.lineContent ?? null,
      content: input.content,
      createdAt: now,
      updatedAt: now,
    });

    return id;
  }

  updateComment(id: string, content: string): boolean {
    const existing = this.commentsById.get(id);
    if (!existing) return false;

    this.commentsById.set(id, {
      ...existing,
      content,
      updatedAt: new Date().toISOString(),
    });

    return true;
  }

  deleteComment(id: string): boolean {
    return this.commentsById.delete(id);
  }

  consumeAll(): string {
    const formatted = this.formattedForAgent;
    this.clear();
    return formatted;
  }

  clear(): void {
    this.commentsById.clear();
  }

  dispose(): void {
    this.clear();
  }
}
