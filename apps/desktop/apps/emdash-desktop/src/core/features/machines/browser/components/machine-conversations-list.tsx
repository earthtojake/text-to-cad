import { EmptyState } from '@emdash/ui/react/components';
import {
  CollectionToolbar,
  CollectionView,
  CollectionViewCell,
  useQueryListSource,
  type CollectionViewColumn,
} from '@emdash/ui/react/patterns';
import { Button, DropdownMenu, Spinner, toast } from '@emdash/ui/react/primitives';
import { useQueryClient } from '@tanstack/react-query';
import { EllipsisIcon, Link2Icon, MessageSquareIcon, Trash2Icon, WifiOffIcon } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useMemo, useState } from 'react';
import { useWorkspaceGroups } from '@core/features/workspaces/api/browser/use-workspace-groups';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import { useSearchFocusHotkeys } from '@core/primitives/keybindings/browser';
import { cn } from '@core/primitives/styling/browser/cn';
import {
  joinMachineConversationRows,
  type MachineConversationItem,
} from '../machine-conversation-rows';
import {
  createMachineConversationsListView,
  type MachineConversationsListViewModel,
} from '../machine-conversations-list-model';
import {
  deleteMachineConversation,
  linkMachineConversation,
  machineConversationsQueryKey,
  useMachineConversations,
  type MachineConversationsScope,
} from '../use-machine-conversations';

const CONVERSATION_COLUMNS: CollectionViewColumn<MachineConversationItem>[] = [
  {
    id: 'icon',
    width: '2.25rem',
    cell: (item) => (
      <span
        className={cn(
          'flex size-7 shrink-0 items-center justify-center rounded-md bg-background-2 text-foreground-muted',
          item.pendingRemoval && 'opacity-60'
        )}
      >
        <MessageSquareIcon className="size-4" />
      </span>
    ),
  },
  {
    id: 'title',
    width: 'minmax(0, 1fr)',
    cell: (item) => (
      <CollectionViewCell
        className={cn(item.pendingRemoval && 'opacity-60')}
        primary={item.conversation.title || 'Untitled'}
        secondary={
          [item.conversation.provider, item.conversation.workspacePath]
            .filter(Boolean)
            .join(' · ') || '-'
        }
      />
    ),
  },
  {
    id: 'status',
    width: 'max-content',
    align: 'center',
    cell: (item) => <ConversationStatusCell item={item} />,
  },
];

/**
 * Every cached conversation record of a host (spec §8) — task-linked and
 * orphaned alike — with per-record link and delete affordances. The list reads
 * this device's registry cache, so it keeps serving (labeled) while the host
 * is unreachable.
 */
export function MachineConversationsList({
  scope,
  hostReachable,
}: {
  scope: MachineConversationsScope;
  hostReachable: boolean;
}) {
  const queryClient = useQueryClient();
  const conversationsQuery = useMachineConversations(scope);
  const openLinkModal = useOpenModal('linkConversationModal');
  const openConfirm = useOpenModal('confirmActionModal');
  const searchRef = useSearchFocusHotkeys();
  const [busyId, setBusyId] = useState<string | null>(null);

  // Dangling-path detection is a client presentation over workspace observations
  // (spec §7.5) — only asserted once the workspace listing for this host has loaded.
  // The mirror serves cached rows even while the host is unreachable, so the
  // subscription is always on; missing workspaces stay listed with their last
  // observation instead of being falsely reported as dangling.
  const workspaceGroups = useWorkspaceGroups(
    scope.kind === 'local' ? { kind: 'local' } : { kind: 'machine', machineId: scope.connectionId },
    true
  ).data;
  const knownWorkspacePaths = useMemo(
    () =>
      workspaceGroups === undefined
        ? undefined
        : new Set(
            workspaceGroups.flatMap((group) => group.workspaces.map((workspace) => workspace.path))
          ),
    [workspaceGroups]
  );

  const items = useMemo(
    () =>
      joinMachineConversationRows({
        conversations: conversationsQuery.data ?? [],
        knownWorkspacePaths,
      }),
    [conversationsQuery.data, knownWorkspacePaths]
  );

  // `items` joins the conversations query with workspace observations, so it
  // stands in for the query's data; loading/error come from the query itself.
  const source = useQueryListSource(
    {
      data: items,
      isLoading: conversationsQuery.isLoading,
      isError: conversationsQuery.isError,
      error: conversationsQuery.error,
    },
    (rows) => rows
  );
  const [view] = useState(() => createMachineConversationsListView(source));

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: machineConversationsQueryKey(scope) });

  const linkConversation = async (item: MachineConversationItem) => {
    const outcome = await openLinkModal({
      connectionId: scope.kind === 'remote' ? scope.connectionId : null,
      conversationTitle: item.conversation.title,
    });
    if (!outcome.success) return;
    setBusyId(item.conversation.id);
    try {
      await linkMachineConversation({
        conversationId: item.conversation.id,
        projectId: outcome.data.projectId,
        taskId: outcome.data.taskId,
      });
      await refresh();
    } catch (error) {
      toast.error('Could not link conversation', {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setBusyId(null);
    }
  };

  const deleteConversation = async (item: MachineConversationItem) => {
    const outcome = await openConfirm({
      title: 'Delete conversation?',
      description: `This permanently deletes “${item.conversation.title}” from its machine. If the machine is offline, the deletion runs when it reconnects.`,
      confirmLabel: 'Delete',
      variant: 'destructive',
    });
    if (!outcome.success) return;
    setBusyId(item.conversation.id);
    try {
      await deleteMachineConversation(item.conversation.id);
      await refresh();
    } catch (error) {
      toast.error('Could not delete conversation', {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setBusyId(null);
    }
  };

  const columns: CollectionViewColumn<MachineConversationItem>[] = [
    ...CONVERSATION_COLUMNS,
    {
      id: 'actions',
      width: '2.5rem',
      align: 'center',
      cell: (item) => (
        <ConversationActionsCell
          item={item}
          busy={busyId === item.conversation.id}
          onLink={() => void linkConversation(item)}
          onDelete={() => void deleteConversation(item)}
        />
      ),
    },
  ];

  return (
    <view.Root>
      <CollectionView
        view={view}
        columns={columns}
        toolbar={
          <ConversationsToolbar
            view={view}
            searchRef={searchRef}
            total={items.length}
            hostReachable={hostReachable}
          />
        }
        errorSlot={
          <EmptyState
            bare
            label="Could not load conversations."
            description={
              conversationsQuery.error instanceof Error
                ? conversationsQuery.error.message
                : String(conversationsQuery.error)
            }
          />
        }
        emptySlot={
          <EmptyState
            bare
            label={
              items.length > 0
                ? 'No conversations match the current search.'
                : 'No conversations on this machine.'
            }
          />
        }
      />
    </view.Root>
  );
}

const ConversationsToolbar = observer(function ConversationsToolbar({
  view,
  searchRef,
  total,
  hostReachable,
}: {
  view: MachineConversationsListViewModel;
  searchRef: React.RefObject<HTMLInputElement | null>;
  total: number;
  hostReachable: boolean;
}) {
  const search = view.useSearch();
  return (
    <CollectionToolbar
      ref={searchRef}
      searchValue={search.query}
      onSearchValueChange={search.setQuery}
      searchPlaceholder="Search conversations, tasks, workspaces…"
      metadata={
        <>
          <span className="text-xs text-foreground-passive tabular-nums">
            {total} {total === 1 ? 'conversation' : 'conversations'}
          </span>
          {!hostReachable && (
            <span className="inline-flex items-center gap-1 rounded-full border border-border-warning px-1.5 py-0.5 text-micro tracking-wide text-foreground-warning uppercase">
              <WifiOffIcon className="size-3" />
              Offline — showing cached records
            </span>
          )}
        </>
      }
    />
  );
});

function ConversationStatusCell({ item }: { item: MachineConversationItem }) {
  const { conversation } = item;
  return (
    <div className={cn('flex items-center gap-2', item.pendingRemoval && 'opacity-60')}>
      {item.linked ? (
        <span
          className="inline-flex max-w-56 shrink-0 items-center gap-1 rounded-full border border-border/70 px-1.5 py-0.5 text-micro tracking-wide text-foreground-muted uppercase"
          title={
            conversation.projectName
              ? `${conversation.projectName} / ${conversation.taskName ?? conversation.taskId}`
              : undefined
          }
        >
          <Link2Icon className="size-3" />
          <span className="truncate normal-case">
            {conversation.taskName ?? conversation.taskId}
          </span>
        </span>
      ) : (
        <Pill tone="warning">Not linked</Pill>
      )}
      {item.missing && <Pill tone="destructive">Missing on host</Pill>}
      {item.dangling && !item.missing && <Pill tone="warning">Workspace removed</Pill>}
      {item.pendingRemoval && (
        <Pill tone="warning" pulse>
          Removal pending…
        </Pill>
      )}
    </div>
  );
}

function ConversationActionsCell({
  item,
  busy,
  onLink,
  onDelete,
}: {
  item: MachineConversationItem;
  busy: boolean;
  onLink: () => void;
  onDelete: () => void;
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="xs"
            icon
            aria-label={`Actions for ${item.conversation.title || 'conversation'}`}
            disabled={busy || item.pendingRemoval}
          />
        }
      >
        {busy ? <Spinner size="sm" /> : <EllipsisIcon className="size-3.5" />}
      </DropdownMenu.Trigger>
      <DropdownMenu.Content align="end">
        <DropdownMenu.Item onClick={onLink}>
          <Link2Icon />
          {item.linked ? 'Link to another task…' : 'Link to a task…'}
        </DropdownMenu.Item>
        <DropdownMenu.Separator />
        <DropdownMenu.Item variant="destructive" onClick={onDelete}>
          <Trash2Icon />
          Delete…
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}

function Pill({
  children,
  tone,
  pulse,
}: {
  children: React.ReactNode;
  tone: 'warning' | 'destructive';
  pulse?: boolean;
}) {
  return (
    <span
      className={cn(
        'shrink-0 rounded-full border px-1.5 py-0.5 text-micro tracking-wide uppercase',
        tone === 'warning' && 'border-border-warning text-foreground-warning',
        tone === 'destructive' && 'border-border-destructive text-foreground-destructive',
        pulse && 'animate-pulse'
      )}
    >
      {children}
    </span>
  );
}
