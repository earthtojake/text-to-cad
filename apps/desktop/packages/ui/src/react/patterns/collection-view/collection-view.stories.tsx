import type { Meta, StoryObj } from '@storybook/react-vite';
import {
  CheckCircle2,
  Clock,
  Folder,
  MoreHorizontal,
  Paintbrush,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import { observer } from 'mobx-react-lite';
import * as React from 'react';
import { EmptyState } from '../../components/empty-state/empty-state';
import { ListPopoverCard } from '../../components/list-popover-card/list-popover-card';
import { Pill } from '../../components/pill/pill';
import { WorkspaceIcon } from '../../components/workspace-icon/workspace-icon';
import { Button } from '../../primitives/button';
import { Checkbox } from '../../primitives/checkbox';
import { DropdownMenu } from '../../primitives/dropdown-menu';
import { Spinner } from '../../primitives/spinner';
import { Switch } from '../../primitives/switch';
import { ToggleGroup } from '../../primitives/toggle';
import { CollectionToolbar } from '../collection-toolbar';
import {
  byField,
  createListView,
  createTextMatcher,
  defineFilter,
  defineSort,
  useQueryListSource,
  type ExternalListSource,
} from '../list-view';
import { CollectionView, CollectionViewCell, type CollectionViewColumn } from './collection-view';
import { SortSelect } from './sort-select';

const meta: Meta = {
  title: 'Patterns/CollectionView',
  parameters: { layout: 'padded' },
};
export default meta;
type Story = StoryObj;

// ══ 1 · Task view — the most demanding state consumer ════════════════════════
// search + Active/Archived filter + SortSelect + multi-select with shift-range
// and a floating bulk bar, in state mode with tabular columns.

interface TaskFixture {
  id: string;
  name: string;
  branch: string;
  adds: number;
  dels: number;
  status: 'active' | 'archived';
  unread: boolean;
  updatedAt: number;
  createdAt: number;
  updatedLabel: string;
}

const TASK_NAMES = [
  'Fix flaky PTY teardown on macOS',
  'Add changelog tab',
  'Migrate settings pages to SettingsSection',
  'Unify list views spec',
  'Investigate SSH reconnect loop',
  'Refactor worktree activation scripts',
  'Polish diff review empty state',
  'Speed up cold boot',
];

const TASKS: TaskFixture[] = Array.from({ length: 57 }, (_, i) => ({
  id: `task-${i}`,
  name: `${TASK_NAMES[i % TASK_NAMES.length]} #${i + 1}`,
  branch: `emdash/task-${i + 1}`,
  adds: (i * 37) % 400,
  dels: (i * 13) % 120,
  status: i % 5 === 4 ? 'archived' : 'active',
  unread: i % 7 === 0,
  updatedAt: 1_000_000 - i * 1_000,
  createdAt: 1_000_000 - i * 2_000,
  updatedLabel: i === 0 ? 'now' : i < 8 ? `${i}h ago` : `${Math.ceil(i / 8)}d ago`,
}));

const tasksView = createListView({
  getItemId: (t: TaskFixture) => t.id,
  source: { kind: 'sync', items: TASKS },
  search: { kind: 'sync', predicate: createTextMatcher((t) => [t.name, t.branch]) },
  filter: defineFilter<TaskFixture, { tab: 'active' | 'archived' }>({
    kind: 'sync',
    initial: { tab: 'active' },
    apply: (t, f) => t.status === f.tab,
  }),
  sort: defineSort<TaskFixture, 'updated' | 'created' | 'unread'>({
    keys: {
      updated: { label: 'Last used', compare: byField((t) => -t.updatedAt) },
      created: { label: 'Created at', compare: byField((t) => -t.createdAt) },
      unread: { label: 'Unread first', compare: byField((t) => (t.unread ? 0 : 1)) },
    },
    initial: { key: 'updated', dir: 'asc' },
  }),
  selection: { kind: 'multi' },
});

/** Hover-revealed checkbox cell — authored as a plain column by the consumer. */
const TaskSelectCell = observer(function TaskSelectCell() {
  const { id } = tasksView.useItem();
  const selection = tasksView.useSelection();
  const checked = selection.isSelected(id);
  return (
    <span
      className="story-select"
      data-checked={checked || undefined}
      onClick={(event) => {
        event.stopPropagation();
        selection.toggle(id, event);
      }}
      style={{ display: 'inline-flex', cursor: 'pointer' }}
    >
      <Checkbox checked={checked} style={{ pointerEvents: 'none' }} aria-label="Select task" />
    </span>
  );
});

const TASK_COLUMNS: CollectionViewColumn<TaskFixture>[] = [
  { id: 'select', width: '1.25rem', cell: () => <TaskSelectCell /> },
  {
    id: 'task',
    width: 'minmax(0, 1fr)',
    cell: (t) => (
      <CollectionViewCell
        primary={
          <>
            {t.unread && (
              <span
                aria-label="Unread"
                style={{
                  display: 'inline-block',
                  width: 6,
                  height: 6,
                  borderRadius: 999,
                  backgroundColor: 'var(--em-accent-9)',
                  marginRight: 6,
                  verticalAlign: 'middle',
                }}
              />
            )}
            {t.name}
          </>
        }
        secondary={t.branch}
      />
    ),
  },
  {
    id: 'diff',
    width: '6rem',
    cell: (t) => (
      <span style={{ fontSize: 'var(--em-text-xs)', fontVariantNumeric: 'tabular-nums' }}>
        <span style={{ color: 'var(--em-foreground-success)' }}>+{t.adds}</span>{' '}
        <span style={{ color: 'var(--em-foreground-error)' }}>−{t.dels}</span>
      </span>
    ),
  },
  {
    id: 'updated',
    width: '5rem',
    cell: (t) => (
      <span style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)' }}>
        {t.updatedLabel}
      </span>
    ),
  },
];

const TasksToolbar = observer(function TasksToolbar() {
  const search = tasksView.useSearch();
  const filter = tasksView.useFilter();
  const sort = tasksView.useSort();
  return (
    <CollectionToolbar
      searchValue={search.query}
      onSearchValueChange={search.setQuery}
      searchPlaceholder="Search tasks…"
      actions={
        <>
          <ToggleGroup.Root
            value={[filter.model.tab]}
            onValueChange={(values: unknown[]) => {
              const next = values[0] as 'active' | 'archived' | undefined;
              if (next) filter.set({ tab: next });
            }}
          >
            <ToggleGroup.Item value="active">Active</ToggleGroup.Item>
            <ToggleGroup.Item value="archived">Archived</ToggleGroup.Item>
          </ToggleGroup.Root>
          <SortSelect sort={sort} />
        </>
      }
    />
  );
});

const TasksSelectionBar = observer(function TasksSelectionBar() {
  const selection = tasksView.useSelection();
  if (selection.count === 0) return null;
  return (
    <ListPopoverCard>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <span style={{ fontSize: 'var(--em-text-sm)', marginRight: '0.25rem' }}>
          {selection.count} selected
        </span>
        <Button variant="secondary" size="xs">
          Archive
        </Button>
        <Button variant="destructive" size="xs">
          <Trash2 />
          Delete
        </Button>
        <Button variant="ghost" size="xs" aria-label="Clear selection" onClick={selection.clear}>
          <X />
        </Button>
      </div>
    </ListPopoverCard>
  );
});

function TaskViewDemo() {
  const [clicked, setClicked] = React.useState<string | null>(null);
  return (
    <div
      style={{
        width: '52rem',
        maxWidth: '100%',
        height: '34rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
      }}
    >
      <style>{`
        .story-select { opacity: 0; transition: opacity 120ms; }
        [data-slot='list-row']:hover .story-select,
        .story-select[data-checked] { opacity: 1; }
      `}</style>
      <div style={{ minHeight: 0, flex: 1, position: 'relative', display: 'flex' }}>
        <tasksView.Root>
          <CollectionView
            view={tasksView}
            columns={TASK_COLUMNS}
            toolbar={<TasksToolbar />}
            footer={<TasksSelectionBar />}
            onItemClick={(t) => setClicked(t.name)}
            emptySlot={<EmptyState label="No tasks" description="No tasks match your search" />}
          />
        </tasksView.Root>
      </div>
      <p style={{ margin: 0, color: 'var(--em-foreground-muted)', fontSize: 'var(--em-text-xs)' }}>
        {clicked === null
          ? 'Row click navigates (logged here); hover a row for its checkbox; shift-click for range select.'
          : `Would navigate to: ${clicked}`}
      </p>
    </div>
  );
}

export const TaskView: Story = {
  name: '1 · Task view (state mode: full stack)',
  render: () => <TaskViewDemo />,
};

// ══ 2 · Worktrees table — shortcut mode with a trailing actions column ═══════
// The simplest call-site shape: plain items, columns, no state layer — plus
// the ellipsis-menu column the real worktrees table has.

interface WorktreeFixture {
  id: string;
  branch: string;
  path: string;
  status: 'active' | 'idle' | 'error';
  adds: number;
  dels: number;
  sizeLabel: string;
  artifactsLabel: string;
  lastUsedLabel: string;
}

const WORKTREES: WorktreeFixture[] = [
  {
    id: 'wt-1',
    branch: 'feature/settings-redesign',
    path: '.worktrees/emdash-settings',
    status: 'active',
    adds: 231,
    dels: 87,
    sizeLabel: '24 MB',
    artifactsLabel: '12 MB artifacts',
    lastUsedLabel: '2 hours ago',
  },
  {
    id: 'wt-2',
    branch: 'feature/status-icons',
    path: '.worktrees/emdash-icons',
    status: 'idle',
    adds: 126,
    dels: 10,
    sizeLabel: '21 MB',
    artifactsLabel: '8 MB artifacts',
    lastUsedLabel: 'Yesterday',
  },
  {
    id: 'wt-3',
    branch: 'fix/pty-teardown',
    path: '.worktrees/emdash-pty',
    status: 'error',
    adds: 12,
    dels: 40,
    sizeLabel: '17 MB',
    artifactsLabel: '2 MB artifacts',
    lastUsedLabel: '3 days ago',
  },
  {
    id: 'wt-4',
    branch: 'chore/deps-bump',
    path: '.worktrees/emdash-deps',
    status: 'idle',
    adds: 4,
    dels: 4,
    sizeLabel: '16 MB',
    artifactsLabel: '0 MB artifacts',
    lastUsedLabel: '1 week ago',
  },
];

function WorktreeActionsCell({ row }: { row: WorktreeFixture }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        render={
          <Button variant="ghost" size="xs" aria-label={`Actions for ${row.branch}`}>
            <MoreHorizontal />
          </Button>
        }
      />
      <DropdownMenu.Content align="end">
        <DropdownMenu.Item>
          <Paintbrush />
          Clean artifacts
        </DropdownMenu.Item>
        <DropdownMenu.Separator />
        <DropdownMenu.Item variant="destructive">
          <Trash2 />
          Delete worktree
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}

const WORKTREE_COLUMNS: CollectionViewColumn<WorktreeFixture>[] = [
  {
    id: 'icon',
    width: '2.25rem',
    cell: (row) => (
      <WorkspaceIcon type="worktree" status={row.status === 'error' ? 'error' : row.status} />
    ),
  },
  {
    id: 'branch',
    width: 'minmax(0, 1fr)',
    cell: (row) => <CollectionViewCell primary={row.branch} secondary={row.path} />,
  },
  {
    id: 'diff',
    width: '6rem',
    cell: (row) => (
      <span style={{ fontSize: 'var(--em-text-xs)', fontVariantNumeric: 'tabular-nums' }}>
        <span style={{ color: 'var(--em-foreground-success)' }}>+{row.adds}</span>{' '}
        <span style={{ color: 'var(--em-foreground-error)' }}>−{row.dels}</span>
      </span>
    ),
  },
  {
    id: 'storage',
    width: '8rem',
    cell: (row) => <CollectionViewCell primary={row.sizeLabel} secondary={row.artifactsLabel} />,
  },
  {
    id: 'usage',
    width: '7rem',
    cell: (row) => (
      <span style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)' }}>
        {row.lastUsedLabel}
      </span>
    ),
  },
  { id: 'actions', width: '2.5rem', cell: (row) => <WorktreeActionsCell row={row} /> },
];

export const WorktreesTable: Story = {
  name: '2 · Worktrees (shortcut mode + actions column)',
  render: () => (
    <div style={{ width: '52rem', maxWidth: '100%', height: '20rem', display: 'flex' }}>
      <CollectionView items={WORKTREES} getItemKey={(row) => row.id} columns={WORKTREE_COLUMNS} />
    </div>
  ),
};

// ══ 3 · Agents — compact density + sections + toolbar search ═════════════════

interface AgentFixture {
  id: string;
  name: string;
  installed: boolean;
}

const AGENTS: AgentFixture[] = [
  { id: 'claude', name: 'Claude Code', installed: true },
  { id: 'codex', name: 'Codex', installed: true },
  { id: 'pi', name: 'Pi', installed: false },
  { id: 'gemini', name: 'Gemini CLI', installed: true },
  { id: 'aider', name: 'Aider', installed: false },
  { id: 'opencode', name: 'OpenCode', installed: false },
  { id: 'goose', name: 'Goose', installed: false },
  { id: 'amp', name: 'Amp', installed: true },
];

const agentsView = createListView({
  getItemId: (a: AgentFixture) => a.id,
  source: { kind: 'sync', items: AGENTS },
  search: { kind: 'sync', predicate: createTextMatcher((a) => a.name) },
  sections: {
    by: (a) => (a.installed ? 'Installed' : 'Not installed'),
    order: ['Installed', 'Not installed'],
  },
});

const AGENT_COLUMNS: CollectionViewColumn<AgentFixture>[] = [
  {
    id: 'name',
    width: 'minmax(0, 1fr)',
    cell: (a) => (
      <span style={{ fontSize: 'var(--em-text-sm)', color: 'var(--em-foreground)' }}>{a.name}</span>
    ),
  },
  {
    id: 'status',
    width: '6rem',
    cell: (a) =>
      a.installed ? (
        <Pill variant="info">Installed</Pill>
      ) : (
        <span style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)' }}>
          Not installed
        </span>
      ),
  },
];

const AgentsToolbar = observer(function AgentsToolbar() {
  const search = agentsView.useSearch();
  return (
    <CollectionToolbar
      searchValue={search.query}
      onSearchValueChange={search.setQuery}
      searchPlaceholder="Search agents…"
    />
  );
});

export const AgentsCompact: Story = {
  name: '3 · Agents (compact density + sections)',
  render: () => (
    <div style={{ width: '36rem', maxWidth: '100%', height: '26rem', display: 'flex' }}>
      <agentsView.Root>
        <CollectionView
          view={agentsView}
          columns={AGENT_COLUMNS}
          density="compact"
          toolbar={<AgentsToolbar />}
          onItemClick={() => {}}
          emptySlot={<EmptyState label="No agents" description="No agents match your search" />}
        />
      </agentsView.Root>
    </div>
  ),
};

// ══ 4 · Automations — freeform rows (`renderRow`) ════════════════════════════
// The least columnar surface: leading enable-switch, two-line body with
// cron/project chips, trailing next-run line. The consumer owns the inner
// layout; the shell stays canonical.

interface AutomationFixture {
  id: string;
  name: string;
  enabled: boolean;
  cronLabel: string;
  project: string | null;
  lastRun: { ok: boolean; label: string } | null;
  nextRunLabel: string | null;
}

const AUTOMATIONS: AutomationFixture[] = [
  {
    id: 'auto-1',
    name: 'Morning triage',
    enabled: true,
    cronLabel: 'Every day at 9 AM',
    project: 'emdash',
    lastRun: { ok: true, label: 'Last run today at 9:00 AM · schedule' },
    nextRunLabel: 'Next run tomorrow at 9:00 AM',
  },
  {
    id: 'auto-2',
    name: 'Dependency bump PRs',
    enabled: true,
    cronLabel: 'Every Monday at 6 AM',
    project: 'emdash',
    lastRun: { ok: false, label: 'Last run Mon at 6:00 AM · schedule' },
    nextRunLabel: 'Next run Mon at 6:00 AM',
  },
  {
    id: 'auto-3',
    name: 'Flaky test sweep',
    enabled: false,
    cronLabel: 'Every day at 2 AM',
    project: null,
    lastRun: null,
    nextRunLabel: null,
  },
];

const CHIP_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '0.25rem',
  borderRadius: 'var(--em-radius-md)',
  backgroundColor: 'var(--em-background-1)',
  padding: '0.125rem 0.5rem',
  fontSize: 'var(--em-text-xs)',
  color: 'var(--em-foreground-muted)',
  whiteSpace: 'nowrap',
};

function AutomationRowContent({ automation }: { automation: AutomationFixture }) {
  const [enabled, setEnabled] = React.useState(automation.enabled);
  return (
    <>
      <span onClick={(event) => event.stopPropagation()} style={{ display: 'inline-flex' }}>
        <Switch checked={enabled} onCheckedChange={setEnabled} aria-label="Enabled" />
      </span>
      <div
        style={{ display: 'flex', flex: 1, minWidth: 0, flexDirection: 'column', gap: '0.375rem' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
          <span
            style={{
              fontSize: 'var(--em-text-sm)',
              color: enabled ? 'var(--em-foreground)' : 'var(--em-foreground-muted)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {automation.name}
          </span>
          <span style={{ flex: 1 }} />
          <span style={CHIP_STYLE}>
            <Clock size={12} />
            {automation.cronLabel}
          </span>
          <span
            style={{
              ...CHIP_STYLE,
              color: automation.project ? CHIP_STYLE.color : 'var(--em-foreground-error)',
            }}
          >
            <Folder size={12} />
            {automation.project ?? 'No project'}
          </span>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.375rem',
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-muted)',
          }}
        >
          {automation.lastRun ? (
            <>
              {automation.lastRun.ok ? (
                <CheckCircle2 size={12} style={{ color: 'var(--em-foreground-success)' }} />
              ) : (
                <XCircle size={12} style={{ color: 'var(--em-foreground-error)' }} />
              )}
              <span>{automation.lastRun.label}</span>
            </>
          ) : (
            <span>No runs</span>
          )}
          <span style={{ flex: 1 }} />
          <span>{automation.nextRunLabel ?? 'Disabled'}</span>
        </div>
      </div>
    </>
  );
}

export const AutomationsFreeform: Story = {
  name: '4 · Automations (freeform renderRow)',
  render: () => (
    <div style={{ width: '48rem', maxWidth: '100%', height: '16rem', display: 'flex' }}>
      <CollectionView
        items={AUTOMATIONS}
        getItemKey={(a) => a.id}
        renderRow={(automation) => <AutomationRowContent automation={automation} />}
        estimateSize={68}
        onItemClick={() => {}}
      />
    </div>
  ),
};

// ══ 5 · Empty / loading / error states ═══════════════════════════════════════
// The three free-form slots. An empty state is mandatory; `EmptyState` is the
// default empty/error content and `Spinner` the loading default. Custom
// `EmptyState` slot content must pass `bare` — the card paints its own
// surface, so the component's panel background would patch over it.

const loadingView = createListView({
  getItemId: (t: TaskFixture) => t.id,
  // Never resolves — keeps the view in its loading state for the story.
  source: { kind: 'async', load: () => new Promise<TaskFixture[]>(() => {}) },
});

const errorView = createListView({
  getItemId: (t: TaskFixture) => t.id,
  source: { kind: 'async', load: () => Promise.reject(new Error('Sync failed')) },
});

function StateCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flex: 1, minWidth: 0 }}>
      <span style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)' }}>
        {label}
      </span>
      <div style={{ height: '14rem', display: 'flex' }}>{children}</div>
    </div>
  );
}

export const States: Story = {
  name: '5 · Empty, loading, and error slots',
  render: () => (
    <div style={{ display: 'flex', gap: '1rem', width: '60rem', maxWidth: '100%' }}>
      <StateCard label="emptySlot (mandatory)">
        <CollectionView
          items={[] as TaskFixture[]}
          getItemKey={(t) => t.id}
          columns={TASK_COLUMNS}
          emptySlot={
            <EmptyState bare label="No tasks" description="Create a task to get started" />
          }
        />
      </StateCard>
      <StateCard label="loadingSlot (state mode)">
        <loadingView.Root>
          <CollectionView
            view={loadingView}
            columns={TASK_COLUMNS}
            emptySlot={<EmptyState bare label="No tasks" />}
            loadingSlot={
              <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
                <Spinner />
              </div>
            }
          />
        </loadingView.Root>
      </StateCard>
      <StateCard label="errorSlot (state mode)">
        <errorView.Root>
          <CollectionView
            view={errorView}
            columns={TASK_COLUMNS}
            emptySlot={<EmptyState bare label="No tasks" />}
            errorSlot={<EmptyState bare label="Could not load tasks" description="Sync failed" />}
          />
        </errorView.Root>
      </StateCard>
    </div>
  ),
};

// ══ 5b · Default slots ════════════════════════════════════════════════════════
// No slot props at all: the built-in defaults (bare `EmptyState`, `Spinner`)
// render correctly on the card surface out of the box.

const defaultLoadingView = createListView({
  getItemId: (t: TaskFixture) => t.id,
  source: { kind: 'async', load: () => new Promise<TaskFixture[]>(() => {}) },
});

const defaultErrorView = createListView({
  getItemId: (t: TaskFixture) => t.id,
  source: { kind: 'async', load: () => Promise.reject(new Error('Sync failed')) },
});

export const DefaultSlots: Story = {
  name: '5b · Default slots (no slot props)',
  render: () => (
    <div style={{ display: 'flex', gap: '1rem', width: '60rem', maxWidth: '100%' }}>
      <StateCard label="default empty">
        <CollectionView
          items={[] as TaskFixture[]}
          getItemKey={(t) => t.id}
          columns={TASK_COLUMNS}
        />
      </StateCard>
      <StateCard label="default loading">
        <defaultLoadingView.Root>
          <CollectionView view={defaultLoadingView} columns={TASK_COLUMNS} />
        </defaultLoadingView.Root>
      </StateCard>
      <StateCard label="default error">
        <defaultErrorView.Root>
          <CollectionView view={defaultErrorView} columns={TASK_COLUMNS} />
        </defaultErrorView.Root>
      </StateCard>
    </div>
  ),
};

// ══ 5c · External source (query-backed) ═══════════════════════════════════════
// `useQueryListSource` mirrors a query result (React Query-shaped) into the
// view: loading/error route through the view's own status and the default
// slots, stale rows stay visible when a refetch fails, and the toolbar stays
// visible throughout. The buttons simulate the query lifecycle.

type QueryPhase = 'loading' | 'ready' | 'load-error' | 'refetch-error';

const QUERY_PHASES: { value: QueryPhase; label: string }[] = [
  { value: 'loading', label: 'Loading' },
  { value: 'ready', label: 'Ready' },
  { value: 'load-error', label: 'Load error' },
  { value: 'refetch-error', label: 'Refetch error' },
];

function buildQueryBackedView(source: ExternalListSource<TaskFixture>) {
  return createListView({
    getItemId: (t: TaskFixture) => t.id,
    source,
    search: {
      kind: 'sync' as const,
      predicate: createTextMatcher((t: TaskFixture) => t.name),
      debounceMs: 0,
    },
  });
}

function QueryBackedStory() {
  const [phase, setPhase] = React.useState<QueryPhase>('loading');

  const hasData = phase === 'ready' || phase === 'refetch-error';
  const source = useQueryListSource<TaskFixture[], TaskFixture>(
    {
      data: hasData ? TASKS.slice(0, 6) : undefined,
      isLoading: phase === 'loading',
      isError: phase === 'load-error' || phase === 'refetch-error',
      error: phase === 'load-error' || phase === 'refetch-error' ? new Error('Sync failed') : null,
    },
    (rows) => rows
  );
  const [view] = React.useState(() => buildQueryBackedView(source));

  return (
    <view.Root>
      <div style={{ width: '46rem', height: '24rem', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', gap: '0.5rem', paddingBottom: '0.75rem' }}>
          <ToggleGroup.Root
            multiple={false}
            value={[phase]}
            onValueChange={([value]) => value && setPhase(value as QueryPhase)}
          >
            {QUERY_PHASES.map((p) => (
              <ToggleGroup.Item key={p.value} value={p.value}>
                {p.label}
              </ToggleGroup.Item>
            ))}
          </ToggleGroup.Root>
        </div>
        <CollectionView
          view={view}
          columns={TASK_COLUMNS}
          toolbar={<QueryBackedToolbar view={view} />}
        />
      </div>
    </view.Root>
  );
}

const QueryBackedToolbar = observer(function QueryBackedToolbar({
  view,
}: {
  view: ReturnType<typeof buildQueryBackedView>;
}) {
  const search = view.useSearch();
  return (
    <CollectionToolbar
      searchValue={search.query}
      onSearchValueChange={search.setQuery}
      searchPlaceholder="Search tasks… (visible in every phase)"
    />
  );
});

export const QueryBacked: Story = {
  name: '5c · External source (query-backed)',
  render: () => <QueryBackedStory />,
};

// ══ 6 · Section header override ══════════════════════════════════════════════
// `renderSectionHeader` replaces the default label+count header — the hook for
// select-all headers like the sidebar conversations list.

const sectionedView = createListView({
  getItemId: (a: AgentFixture) => a.id,
  source: { kind: 'sync', items: AGENTS },
  sections: {
    by: (a) => (a.installed ? 'Installed' : 'Not installed'),
    order: ['Installed', 'Not installed'],
  },
  selection: { kind: 'multi' },
});

const SectionedRowCell = observer(function SectionedRowCell({ agent }: { agent: AgentFixture }) {
  const { id } = sectionedView.useItem();
  const selection = sectionedView.useSelection();
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      <span onClick={(event) => event.stopPropagation()} style={{ display: 'inline-flex' }}>
        <Checkbox
          checked={selection.isSelected(id)}
          onCheckedChange={() => selection.toggle(id)}
          aria-label={`Select ${agent.name}`}
        />
      </span>
      <span style={{ fontSize: 'var(--em-text-sm)' }}>{agent.name}</span>
    </span>
  );
});

const SectionSelectAllHeader = observer(function SectionSelectAllHeader({
  sectionKey,
  count,
}: {
  sectionKey: string;
  count: number;
}) {
  const selection = sectionedView.useSelection();
  const ids = AGENTS.filter(
    (a) => (a.installed ? 'Installed' : 'Not installed') === sectionKey
  ).map((a) => a.id);
  const selectedInSection = ids.filter((id) => selection.isSelected(id)).length;
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        padding: '0.5rem 0.75rem',
        fontSize: 'var(--em-text-xs)',
        color: 'var(--em-foreground-muted)',
      }}
    >
      <Checkbox
        checked={selectedInSection === count}
        indeterminate={selectedInSection > 0 && selectedInSection < count}
        onCheckedChange={() => {
          for (const id of ids) {
            if ((selectedInSection === count) === selection.isSelected(id)) selection.toggle(id);
          }
        }}
        aria-label={`Select all in ${sectionKey}`}
      />
      <span>
        {sectionKey} ({count})
      </span>
    </div>
  );
});

export const SectionHeaderOverride: Story = {
  name: '6 · Section header override (select-all)',
  render: () => (
    <div style={{ width: '32rem', maxWidth: '100%', height: '24rem', display: 'flex' }}>
      <sectionedView.Root>
        <CollectionView
          view={sectionedView}
          renderRow={(agent) => <SectionedRowCell agent={agent} />}
          density="compact"
          renderSectionHeader={(key, count) => (
            <SectionSelectAllHeader sectionKey={key} count={count} />
          )}
          emptySlot={<EmptyState label="No agents" />}
        />
      </sectionedView.Root>
    </div>
  ),
};
