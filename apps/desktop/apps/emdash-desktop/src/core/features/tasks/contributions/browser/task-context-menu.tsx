import { ContextMenu, DropdownMenu, toast } from '@emdash/ui/react/primitives';
import { Archive, Copy, Pencil, Pin, PinOff, RotateCcw, Trash2 } from 'lucide-react';
import React from 'react';

interface TaskMenuActions {
  isPinned: boolean;
  canPin: boolean;
  isArchived: boolean;
  archiveDisabledReason?: string;
  branchName?: string;
  onPin: () => void;
  onUnpin: () => void;
  onRename: () => void;
  onArchive?: () => void;
  onRestore?: () => void;
  onReconnect?: () => void;
  onDelete: () => void;
}

interface TaskContextMenuProps extends TaskMenuActions {
  children: React.ReactNode;
}

interface TaskDropdownMenuProps extends TaskMenuActions {
  trigger: React.ReactElement;
}

export function TaskContextMenu({ children, ...actions }: TaskContextMenuProps) {
  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{children}</ContextMenu.Trigger>
      <ContextMenu.Content>
        <TaskMenuItems kind="context" {...actions} />
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
}

/** Visible Codex-style counterpart to the right-click menu. */
export function TaskDropdownMenu({ trigger, ...actions }: TaskDropdownMenuProps) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger render={trigger} />
      <DropdownMenu.Content align="end" onClick={(event) => event.stopPropagation()}>
        <TaskMenuItems kind="dropdown" {...actions} />
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}

function TaskMenuItems({
  kind,
  isPinned,
  canPin,
  isArchived,
  archiveDisabledReason,
  branchName,
  onPin,
  onUnpin,
  onRename,
  onArchive,
  onRestore,
  onReconnect,
  onDelete,
}: TaskMenuActions & { kind: 'context' | 'dropdown' }) {
  const archiveDisabledReasonId = React.useId();
  const handleCopyBranchName = useCopyBranchName(branchName);

  return (
    <>
      {canPin &&
        (isPinned ? (
          <TaskMenuItem kind={kind} onClick={onUnpin}>
            <PinOff className="size-4" />
            Unpin chat
          </TaskMenuItem>
        ) : (
          <TaskMenuItem kind={kind} onClick={onPin}>
            <Pin className="size-4" />
            Pin chat
          </TaskMenuItem>
        ))}
      <TaskMenuItem kind={kind} onClick={onRename}>
        <Pencil className="size-4" />
        Rename
      </TaskMenuItem>
      {onReconnect && (
        <TaskMenuItem kind={kind} onClick={onReconnect}>
          <RotateCcw className="size-4" />
          Reconnect
        </TaskMenuItem>
      )}
      {!isArchived && onArchive && (
        <TaskMenuItem
          kind={kind}
          disabled={!!archiveDisabledReason}
          aria-describedby={archiveDisabledReason ? archiveDisabledReasonId : undefined}
          onClick={onArchive}
        >
          <Archive className="size-4" />
          Archive
        </TaskMenuItem>
      )}
      {archiveDisabledReason && (
        <span id={archiveDisabledReasonId} className="sr-only">
          {archiveDisabledReason}
        </span>
      )}
      {isArchived && onRestore && (
        <TaskMenuItem kind={kind} onClick={onRestore}>
          <RotateCcw className="size-4" />
          Restore
        </TaskMenuItem>
      )}
      {branchName && (
        <TaskMenuItem kind={kind} onClick={() => void handleCopyBranchName()}>
          <Copy className="size-4" />
          Copy branch name
        </TaskMenuItem>
      )}
      <TaskMenuSeparator kind={kind} />
      <TaskMenuItem kind={kind} variant="destructive" onClick={onDelete}>
        <Trash2 className="size-4" />
        Delete
      </TaskMenuItem>
    </>
  );
}

function TaskMenuItem({
  kind,
  ...props
}: {
  kind: 'context' | 'dropdown';
  children: React.ReactNode;
  disabled?: boolean;
  variant?: 'default' | 'destructive';
  onClick?: () => void;
  'aria-describedby'?: string;
}) {
  return kind === 'context' ? <ContextMenu.Item {...props} /> : <DropdownMenu.Item {...props} />;
}

function TaskMenuSeparator({ kind }: { kind: 'context' | 'dropdown' }) {
  return kind === 'context' ? <ContextMenu.Separator /> : <DropdownMenu.Separator />;
}

function useCopyBranchName(branchName: string | undefined): () => Promise<void> {
  return React.useCallback(async () => {
    if (!branchName) return;

    try {
      await navigator.clipboard.writeText(branchName);
      toast('Branch name copied');
    } catch {
      toast.error('Copy failed', {
        description: 'The branch name could not be copied to the clipboard.',
      });
    }
  }, [branchName]);
}
