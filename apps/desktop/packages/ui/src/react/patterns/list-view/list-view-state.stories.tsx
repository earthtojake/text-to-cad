/**
 * Stories for the headless `createListView` factory — the state layer that
 * powers `CollectionView` (the page-level list pattern; see
 * Patterns/CollectionView). These stories render through the raw chrome to
 * exercise the factory in isolation.
 *
 * Each story demonstrates a different capability combination using a simple
 * Agent fixture type.  The observer-wrapped rows access the store through
 * the factory's hooks — no prop-drilling required.
 */
import type { Meta, StoryObj } from '@storybook/react-vite';
import { observer } from 'mobx-react-lite';
import * as React from 'react';
import { SearchInput } from '../../primitives/search-input';
import { byField } from './comparators';
import { createListView } from './core/create-list-view';
import { defineFilter, defineSort } from './core/define-helpers';
import { ListView } from './index';
import { createTextMatcher } from './matching';
import * as s from '../../story-layout.css';

const meta: Meta = {
  title: 'Patterns/ListView/State (createListView)',
  parameters: { layout: 'padded' },
};
export default meta;
type Story = StoryObj;

// ── Fixture ───────────────────────────────────────────────────────────────────

interface Agent {
  id: string;
  name: string;
  description: string;
  status: 'installed' | 'not-installed';
  category: 'recommended' | 'community';
}

const ALL_AGENTS: Agent[] = [
  {
    id: '1',
    name: 'Claude Sonnet',
    description: "Anthropic's flagship coding agent",
    status: 'installed',
    category: 'recommended',
  },
  {
    id: '2',
    name: 'OpenAI Codex',
    description: 'Code generation from OpenAI',
    status: 'installed',
    category: 'recommended',
  },
  {
    id: '3',
    name: 'Gemini',
    description: "Google's AI coding assistant",
    status: 'not-installed',
    category: 'recommended',
  },
  {
    id: '4',
    name: 'Aider',
    description: 'AI pair programmer in your terminal',
    status: 'not-installed',
    category: 'community',
  },
  {
    id: '5',
    name: 'GitHub Copilot',
    description: 'AI coding suggestions from GitHub',
    status: 'installed',
    category: 'recommended',
  },
  {
    id: '6',
    name: 'Mentat',
    description: 'Code-editing AI assistant',
    status: 'not-installed',
    category: 'community',
  },
  {
    id: '7',
    name: 'Continue',
    description: 'Open-source coding assistant',
    status: 'not-installed',
    category: 'community',
  },
  {
    id: '8',
    name: 'Cursor Agent',
    description: "Cursor's built-in agent mode",
    status: 'installed',
    category: 'community',
  },
];

// ── Shared row styles ─────────────────────────────────────────────────────────

function AgentRowBase({
  agent,
  selected,
  renaming,
  onRename,
  onClick,
  isLast,
}: {
  agent: Agent;
  selected?: boolean;
  renaming?: boolean;
  onRename?: (name: string) => void;
  onClick?: (e: React.MouseEvent) => void;
  isLast: boolean;
}) {
  const [draft, setDraft] = React.useState(agent.name);

  return (
    <ListView.Row interactive isLast={isLast} selected={selected} onClick={onClick}>
      <div style={{ minWidth: 0, flex: 1 }}>
        {renaming ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => onRename?.(draft)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onRename?.(draft);
              if (e.key === 'Escape') onRename?.(agent.name);
            }}
            style={{
              fontSize: 'var(--em-text-sm)',
              width: '100%',
              background: 'none',
              border: '1px solid var(--em-border)',
              borderRadius: 4,
              padding: '0 4px',
            }}
          />
        ) : (
          <div
            style={{
              fontSize: 'var(--em-text-sm)',
              fontWeight: 400,
              color: 'var(--em-foreground)',
            }}
          >
            {agent.name}
          </div>
        )}
        <div
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-muted)',
            marginTop: 1,
          }}
        >
          {agent.description}
        </div>
      </div>
      {agent.status === 'installed' && (
        <span
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-status-success)',
            flexShrink: 0,
          }}
        >
          Installed
        </span>
      )}
    </ListView.Row>
  );
}

// ── 1. Search (sync) ──────────────────────────────────────────────────────────

const searchView = createListView({
  getItemId: (a: Agent) => a.id,
  source: { kind: 'sync', items: ALL_AGENTS },
  search: { kind: 'sync', predicate: createTextMatcher((a) => [a.name, a.description]) },
});

const SearchRow = observer(function SearchRow({
  agent,
  isLast,
}: {
  agent: Agent;
  isLast: boolean;
}) {
  return <AgentRowBase agent={agent} isLast={isLast} />;
});

function SearchDemo() {
  const search = searchView.useSearch();
  const { visibleItems } = searchView.useListView();
  return (
    <ListView>
      <ListView.Toolbar>
        <SearchInput
          size="sm"
          value={search.query}
          onChange={(e) => search.setQuery(e.target.value)}
          onClear={() => search.setQuery('')}
          placeholder="Search agents…"
        />
      </ListView.Toolbar>
      <ListView.Body>
        <searchView.List
          renderItem={(agent, i) => (
            <SearchRow key={agent.id} agent={agent} isLast={i === visibleItems.length - 1} />
          )}
          emptySlot={
            <div
              style={{
                padding: '2rem',
                textAlign: 'center',
                color: 'var(--em-foreground-muted)',
                fontSize: 'var(--em-text-sm)',
              }}
            >
              No agents match your search.
            </div>
          }
        />
      </ListView.Body>
    </ListView>
  );
}

export const Search: Story = {
  name: 'Search (sync)',
  render: () => (
    <div className={s.w96} style={{ height: '28rem', display: 'flex', flexDirection: 'column' }}>
      <searchView.Root>
        <SearchDemo />
      </searchView.Root>
    </div>
  ),
};

// ── 2. Filter + Sort ──────────────────────────────────────────────────────────

const filterSortView = createListView({
  getItemId: (a: Agent) => a.id,
  source: { kind: 'sync', items: ALL_AGENTS },
  search: { kind: 'sync', predicate: createTextMatcher((a) => a.name) },
  filter: defineFilter<Agent, { status: 'all' | 'installed' | 'not-installed' }>({
    kind: 'sync',
    initial: { status: 'all' },
    apply: (a, f) => f.status === 'all' || a.status === f.status,
  }),
  sort: defineSort<Agent, 'name' | 'status'>({
    keys: {
      name: { label: 'Name', compare: byField((a) => a.name) },
      status: { label: 'Status', compare: byField((a) => a.status) },
    },
    initial: { key: 'name', dir: 'asc' },
  }),
});

const FilterSortRow = observer(function FilterSortRow({
  agent,
  isLast,
}: {
  agent: Agent;
  isLast: boolean;
}) {
  return <AgentRowBase agent={agent} isLast={isLast} />;
});

function FilterSortDemo() {
  const search = filterSortView.useSearch();
  const filter = filterSortView.useFilter();
  const sort = filterSortView.useSort();
  const { visibleItems } = filterSortView.useListView();

  const statusOpts = ['all', 'installed', 'not-installed'] as const;

  return (
    <ListView>
      <ListView.Toolbar>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          {statusOpts.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => filter.set({ status: s })}
              style={{
                padding: '2px 8px',
                borderRadius: 4,
                border: '1px solid var(--em-border)',
                background: filter.model.status === s ? 'var(--em-accent-9)' : 'none',
                color:
                  filter.model.status === s ? 'var(--em-accent-contrast)' : 'var(--em-foreground)',
                cursor: 'pointer',
                fontSize: 'var(--em-text-xs)',
              }}
            >
              {s}
            </button>
          ))}
          <SearchInput
            size="sm"
            value={search.query}
            onChange={(e) => search.setQuery(e.target.value)}
            onClear={() => search.setQuery('')}
            placeholder="Search…"
            style={{ flex: 1 }}
          />
          <button
            type="button"
            onClick={() => sort.toggleDir()}
            style={{
              fontSize: 'var(--em-text-xs)',
              cursor: 'pointer',
              background: 'none',
              border: '1px solid var(--em-border)',
              borderRadius: 4,
              padding: '2px 8px',
              color: 'var(--em-foreground)',
            }}
          >
            Name {sort.dir === 'asc' ? '↑' : '↓'}
          </button>
        </div>
      </ListView.Toolbar>
      <ListView.Body>
        <filterSortView.List
          renderItem={(agent, i) => (
            <FilterSortRow key={agent.id} agent={agent} isLast={i === visibleItems.length - 1} />
          )}
          emptySlot={
            <div
              style={{
                padding: '2rem',
                textAlign: 'center',
                color: 'var(--em-foreground-muted)',
                fontSize: 'var(--em-text-sm)',
              }}
            >
              No results.
            </div>
          }
        />
      </ListView.Body>
    </ListView>
  );
}

export const FilterAndSort: Story = {
  name: 'Filter + Sort',
  render: () => (
    <div className={s.w96} style={{ height: '28rem', display: 'flex', flexDirection: 'column' }}>
      <filterSortView.Root>
        <FilterSortDemo />
      </filterSortView.Root>
    </div>
  ),
};

// ── 3. Multi-select + sections ────────────────────────────────────────────────

const selectView = createListView({
  getItemId: (a: Agent) => a.id,
  source: { kind: 'sync', items: ALL_AGENTS },
  selection: { kind: 'multi' },
  sections: { by: (a) => a.category, order: ['recommended', 'community'] },
});

const SelectRow = observer(function SelectRow({
  agent,
  isLast,
}: {
  agent: Agent;
  isLast: boolean;
}) {
  const sel = selectView.useSelection();
  return (
    <AgentRowBase
      agent={agent}
      isLast={isLast}
      selected={sel.isSelected(agent.id)}
      onClick={(e) => sel.toggle(agent.id, e)}
    />
  );
});

function SelectDemo() {
  const sel = selectView.useSelection();

  return (
    <ListView>
      <ListView.Toolbar>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-muted)',
          }}
        >
          <button
            type="button"
            onClick={sel.count === ALL_AGENTS.length ? sel.clear : sel.selectAll}
            style={{
              cursor: 'pointer',
              background: 'none',
              border: 'none',
              color: 'var(--em-foreground-muted)',
              fontSize: 'var(--em-text-xs)',
            }}
          >
            {sel.count === ALL_AGENTS.length ? 'Deselect all' : 'Select all'}
          </button>
          {sel.count > 0 && <span>{sel.count} selected</span>}
        </div>
      </ListView.Toolbar>
      <ListView.Body>
        <selectView.List
          renderItem={(agent, i) => (
            <SelectRow key={agent.id} agent={agent} isLast={i === ALL_AGENTS.length - 1} />
          )}
          renderSection={(key, count) => <ListView.SectionHeader label={key} count={count} />}
        />
      </ListView.Body>
      {sel.count > 0 && (
        <ListView.Footer>
          <div
            style={{
              margin: '0.5rem',
              padding: '0.5rem 0.75rem',
              borderRadius: 'var(--em-radius-md)',
              backgroundColor: 'var(--em-surface-overlay)',
              border: '1px solid var(--em-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: 'var(--em-text-sm)',
            }}
          >
            <span style={{ color: 'var(--em-foreground)' }}>{sel.count} items selected</span>
            <button
              type="button"
              onClick={sel.clear}
              style={{
                fontSize: 'var(--em-text-xs)',
                color: 'var(--em-foreground-muted)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Clear
            </button>
          </div>
        </ListView.Footer>
      )}
    </ListView>
  );
}

export const MultiSelectSections: Story = {
  name: 'Multi-select + Sections',
  render: () => (
    <div
      className={s.w96}
      style={{ height: '32rem', display: 'flex', flexDirection: 'column', position: 'relative' }}
    >
      <selectView.Root>
        <SelectDemo />
      </selectView.Root>
    </div>
  ),
};

// ── 4. Inline rename ──────────────────────────────────────────────────────────

const renameView = createListView({
  getItemId: (a: Agent) => a.id,
  source: { kind: 'sync', items: ALL_AGENTS },
  rename: {
    canRename: () => true,
    commit: async (agent, name) => {
      // eslint-disable-next-line no-console
      console.log('rename', agent.id, '->', name);
    },
  },
});

const RenameRow = observer(function RenameRow({
  agent,
  isLast,
}: {
  agent: Agent;
  isLast: boolean;
}) {
  const rename = renameView.useRename();
  return (
    <AgentRowBase
      agent={agent}
      isLast={isLast}
      renaming={rename.editingId === agent.id}
      onRename={(name) => void rename.commit(name)}
      onClick={() => {
        if (rename.editingId !== agent.id && rename.canRename(agent)) {
          rename.begin(agent.id);
        }
      }}
    />
  );
});

function RenameDemo() {
  return (
    <ListView>
      <ListView.Toolbar>
        <p
          style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)', margin: 0 }}
        >
          Click a row to rename it.
        </p>
      </ListView.Toolbar>
      <ListView.Body>
        <renameView.List
          renderItem={(agent, i) => (
            <RenameRow key={agent.id} agent={agent} isLast={i === ALL_AGENTS.length - 1} />
          )}
        />
      </ListView.Body>
    </ListView>
  );
}

export const InlineRename: Story = {
  name: 'Inline rename',
  render: () => (
    <div className={s.w96} style={{ height: '28rem', display: 'flex', flexDirection: 'column' }}>
      <renameView.Root>
        <RenameDemo />
      </renameView.Root>
    </div>
  ),
};

// ── 5. Infinite scroll (async pagination) ─────────────────────────────────────

function makeAgentPage(start: number, count: number): Agent[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `page-${start + i}`,
    name: `Agent ${start + i + 1}`,
    description: `Auto-generated agent #${start + i + 1}`,
    status: (start + i) % 2 === 0 ? 'installed' : 'not-installed',
    category: 'community',
  }));
}

const infiniteView = createListView({
  getItemId: (a: Agent) => a.id,
  source: { kind: 'sync', items: [] },
  pagination: {
    kind: 'infinite',
    loadMore: async (cursor) => {
      const page = cursor ? parseInt(cursor, 10) : 0;
      await new Promise((r) => setTimeout(r, 600));
      const items = makeAgentPage(page * 10, 10);
      return { items, nextCursor: page < 4 ? String(page + 1) : null };
    },
  },
});

const InfiniteRow = observer(function InfiniteRow({
  agent,
  isLast,
}: {
  agent: Agent;
  isLast: boolean;
}) {
  return <AgentRowBase agent={agent} isLast={isLast} />;
});

function InfiniteDemo() {
  const pg = infiniteView.usePagination();
  const { visibleItems } = infiniteView.useListView();

  return (
    <ListView>
      <ListView.Toolbar>
        <p
          style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)', margin: 0 }}
        >
          {visibleItems.length} loaded — {pg.hasMore ? 'scroll to load more' : 'all loaded'}
        </p>
      </ListView.Toolbar>
      <ListView.Body>
        <infiniteView.List
          renderItem={(agent, i) => (
            <InfiniteRow key={agent.id} agent={agent} isLast={i === visibleItems.length - 1} />
          )}
          loadingSlot={
            <div
              style={{
                padding: '2rem',
                textAlign: 'center',
                color: 'var(--em-foreground-muted)',
                fontSize: 'var(--em-text-sm)',
              }}
            >
              Loading…
            </div>
          }
        />
      </ListView.Body>
    </ListView>
  );
}

export const InfiniteScroll: Story = {
  name: 'Infinite scroll (pagination)',
  render: () => (
    <div className={s.w96} style={{ height: '28rem', display: 'flex', flexDirection: 'column' }}>
      <infiniteView.Root>
        <InfiniteDemo />
      </infiniteView.Root>
    </div>
  ),
};

// ── 6. StaticList (popover, no virtualizer) ───────────────────────────────────

const staticView = createListView({
  getItemId: (a: Agent) => a.id,
  source: { kind: 'sync', items: ALL_AGENTS.slice(0, 5) },
  search: { kind: 'sync', predicate: createTextMatcher((a) => a.name) },
});

function StaticDemo() {
  const search = staticView.useSearch();

  return (
    <div
      style={{
        border: '1px solid var(--em-border)',
        borderRadius: 'var(--em-radius-md)',
        width: 280,
        overflow: 'hidden',
        backgroundColor: 'var(--em-surface-base)',
      }}
    >
      <div style={{ padding: '0.5rem' }}>
        <SearchInput
          size="sm"
          value={search.query}
          onChange={(e) => search.setQuery(e.target.value)}
          onClear={() => search.setQuery('')}
          placeholder="Filter…"
        />
      </div>
      <staticView.StaticList
        renderItem={(agent, i) => (
          <ListView.Row key={agent.id} interactive isLast={i === 4}>
            <span style={{ fontSize: 'var(--em-text-sm)', color: 'var(--em-foreground)' }}>
              {agent.name}
            </span>
          </ListView.Row>
        )}
        emptySlot={
          <div
            style={{
              padding: '0.5rem 1rem',
              fontSize: 'var(--em-text-sm)',
              color: 'var(--em-foreground-muted)',
            }}
          >
            No results.
          </div>
        }
      />
    </div>
  );
}

export const StaticList: Story = {
  name: 'StaticList (popover escape hatch)',
  render: () => (
    <div style={{ padding: '2rem' }}>
      <staticView.Root>
        <StaticDemo />
      </staticView.Root>
    </div>
  ),
};
