import { EmptyState } from '@emdash/ui/react/components';
import { Combobox, Tooltip } from '@emdash/ui/react/primitives';
import { ChevronsUpDown, FolderGit2, GitBranch, Link } from 'lucide-react';
import { useState } from 'react';
import type { ProjectWorkspaceOption } from '@core/features/tasks/api/browser/create-task-modal/project-workspace-options';
import { cn } from '@core/primitives/styling/browser/cn';

function workspaceLabel(ws: ProjectWorkspaceOption): string {
  if (ws.kind === 'repository') return 'Repository root';
  if (ws.path) {
    const lastSegment = ws.path.split('/').at(-1);
    return lastSegment || (ws.branchName ?? ws.workspaceId ?? ws.path);
  }
  return ws.branchName ?? ws.workspaceId ?? ws.path;
}

function WorkspaceItemContent({ ws }: { ws: ProjectWorkspaceOption }) {
  const isRoot = ws.kind === 'repository';
  const label = workspaceLabel(ws);
  const hasDiff = ws.linesAdded != null || ws.linesDeleted != null;

  return (
    <span className="flex min-w-0 flex-1 flex-col gap-1.5">
      <span className={cn('shrink-0 flex items-center gap-1.5')}>
        {isRoot ? <FolderGit2 className="size-3.5" /> : <GitBranch className="size-3.5" />}
        <span className="truncate text-sm leading-none">{label}</span>
        {hasDiff && (
          <span className="ml-1 text-xs text-foreground-muted">
            {ws.linesAdded != null && (
              <span className="text-foreground-diff-added">+{ws.linesAdded}</span>
            )}
            {ws.linesDeleted != null && (
              <span className="ml-1 text-foreground-diff-deleted">−{ws.linesDeleted}</span>
            )}
          </span>
        )}
        {ws.linkedTaskCount > 0 && (
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger className="ml-1 flex items-center gap-0.5 text-xs text-foreground-info">
                <Link className="size-3" />
                {ws.linkedTaskCount}
              </Tooltip.Trigger>
              <Tooltip.Content>
                {ws.linkedTaskCount === 1
                  ? '1 associated task'
                  : `${ws.linkedTaskCount} associated tasks`}
              </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
        )}
      </span>
      <span className="truncate text-left text-xs leading-snug text-foreground-muted">
        {ws.disabledReason ?? ws.path}
      </span>
    </span>
  );
}
interface ExistingWorkspacePickerProps {
  workspaces: ProjectWorkspaceOption[];
  isLoading: boolean;
  selectedWorkspaceId: string | null;
  onSelect: (workspaceId: string) => void;
}

export function ExistingWorkspacePicker({
  workspaces,
  isLoading,
  selectedWorkspaceId,
  onSelect,
}: ExistingWorkspacePickerProps) {
  const [query, setQuery] = useState('');

  const selected = workspaces.find((ws) => ws.workspaceId === selectedWorkspaceId) ?? null;

  const filtered = query
    ? workspaces.filter((ws) => {
        const q = query.toLowerCase();
        return workspaceLabel(ws).toLowerCase().includes(q) || ws.path.toLowerCase().includes(q);
      })
    : workspaces;

  if (isLoading) {
    return (
      <div className="flex h-9 items-center justify-center text-xs text-foreground-muted">
        Loading workspaces…
      </div>
    );
  }

  if (workspaces.length === 0) {
    return (
      <p className="text-xs text-foreground-muted">
        No existing workspaces found for this project.
      </p>
    );
  }

  return (
    <Combobox.Root
      value={selected}
      onValueChange={(ws: ProjectWorkspaceOption | null) => {
        if (ws?.workspaceId && !ws.disabledReason) onSelect(ws.workspaceId);
      }}
      onOpenChange={(open) => {
        if (!open) setQuery('');
      }}
      isItemEqualToValue={(a: ProjectWorkspaceOption, b: ProjectWorkspaceOption) => a.key === b.key}
    >
      <Combobox.Trigger className="data-popup-open:border-ring flex w-full items-center justify-between gap-2 rounded-lg border border-border px-2.5 py-2 text-sm transition-colors outline-none hover:bg-background-2">
        {selected ? (
          <WorkspaceItemContent ws={selected} />
        ) : (
          <span className="text-foreground-muted">Select a workspace…</span>
        )}
        <ChevronsUpDown className="size-4 shrink-0 text-foreground-passive" />
      </Combobox.Trigger>
      <Combobox.Content>
        <Combobox.Input
          value={query}
          onChange={(e) => setQuery((e.target as HTMLInputElement).value)}
          placeholder="Search workspaces…"
          showTrigger={false}
        />
        <Combobox.List className="max-h-52 overflow-y-auto p-1!">
          {filtered.map((ws) => (
            <Combobox.Item
              key={ws.key}
              value={ws}
              disabled={!!ws.disabledReason}
              showCheck={false}
              className="items-start py-2 pr-3"
            >
              <WorkspaceItemContent ws={ws} />
            </Combobox.Item>
          ))}
          {filtered.length === 0 && (
            <EmptyState label="No workspaces found" className="border-none bg-transparent" />
          )}
        </Combobox.List>
      </Combobox.Content>
    </Combobox.Root>
  );
}
