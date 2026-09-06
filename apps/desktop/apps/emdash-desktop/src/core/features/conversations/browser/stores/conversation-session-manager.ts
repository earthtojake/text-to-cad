import { reaction } from 'mobx';
import type { ConversationStore } from '@core/features/conversations/api/browser/conversation-manager';
import { conversationRegistry } from '@core/features/conversations/api/browser/stores/conversation-registry';
import { log } from '@core/primitives/logging/browser/logger';
import { ConversationHydrationReconciler } from './conversation-hydration-reconciler';

/**
 * Per-task manager that controls conversation PTY-session lifecycle via acquire/release.
 *
 * Thin adapter over ConversationHydrationReconciler: converts the ref-counted
 * acquire/release interface (one call per tab open/close) into the set-diff sync()
 * the reconciler uses.
 *
 * Ref-counting supports the same conversation being open in multiple panes
 * (e.g. restored from a snapshot). The session stays hydrated until the last
 * tab closes.
 *
 * The reconciler handles grace timers and retry logic for dehydration.
 */
export class ConversationSessionManager {
  private readonly _reconciler: ConversationHydrationReconciler;
  private readonly _disposeHostReaction: () => void;
  /** Ref counts per conversationId — session stays alive while count > 0. */
  private readonly _refCounts = new Map<string, number>();

  constructor(private readonly taskId: string) {
    this._reconciler = new ConversationHydrationReconciler({
      taskId,
      getConversations: () => conversationRegistry.get(taskId),
      log,
    });
    this._disposeHostReaction = reaction(
      () => conversationRegistry.get(taskId)?.hostAccess?.state.kind,
      (kind) => {
        if (kind === 'ready') this.sync();
      }
    );
  }

  /**
   * Start the PTY session for this conversation (if not already running).
   * Returns the ConversationStore, or undefined if the conversation is not found.
   */
  acquire(conversationId: string): ConversationStore | undefined {
    this._refCounts.set(conversationId, (this._refCounts.get(conversationId) ?? 0) + 1);
    this.sync();
    return conversationRegistry.get(this.taskId)?.conversations.get(conversationId);
  }

  /**
   * Signal that this conversation's tab has been closed.
   * The reconciler will dehydrate the PTY session after a grace period
   * once the last reference is released.
   */
  release(conversationId: string): void {
    const count = this._refCounts.get(conversationId) ?? 0;
    if (count <= 1) {
      this._refCounts.delete(conversationId);
    } else {
      this._refCounts.set(conversationId, count - 1);
    }
    this.sync();
  }

  dispose(): void {
    this._disposeHostReaction();
    this._reconciler.dispose();
    this._refCounts.clear();
  }

  private sync(): void {
    if (conversationRegistry.get(this.taskId)?.hostAccess?.liveAction.kind === 'disabled') return;
    this._reconciler.sync(new Set(this._refCounts.keys()));
  }
}

const _registry = new Map<string, ConversationSessionManager>();

export function getConversationSessionManager(taskId: string): ConversationSessionManager {
  const existing = _registry.get(taskId);
  if (existing) return existing;
  const manager = new ConversationSessionManager(taskId);
  _registry.set(taskId, manager);
  return manager;
}

export function releaseConversationSessionManager(taskId: string): void {
  const manager = _registry.get(taskId);
  if (!manager) return;
  manager.dispose();
  _registry.delete(taskId);
}
