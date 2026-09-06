/**
 * Stories for the raw `ListView` chrome — an internal escape hatch. Page-level
 * lists render through `CollectionView` (see Patterns/CollectionView); compose
 * this chrome directly only when a surface cannot fit that shell.
 */
import type { Meta, StoryObj } from '@storybook/react-vite';
import {
  CheckIcon,
  FilterIcon,
  GlobeIcon,
  LayoutListIcon,
  PackageIcon,
  TerminalIcon,
} from 'lucide-react';
import * as React from 'react';
import { SearchInput } from '../../primitives/search-input';
import { Tabs } from '../../primitives/tabs/tabs';
import { ListView } from './index';
import * as s from '../../story-layout.css';

const meta: Meta = {
  title: 'Patterns/ListView/Chrome (escape hatch)',
  parameters: { layout: 'padded' },
};
export default meta;
type Story = StoryObj;

// ── Helpers ───────────────────────────────────────────────────────────────────

interface FlatItem {
  id: string;
  title: string;
  subtitle: string;
  status: 'open' | 'closed' | 'merged';
}

const STATUS_COLOR: Record<FlatItem['status'], string> = {
  open: '#22c55e',
  closed: '#ef4444',
  merged: '#a855f7',
};

function makeFlatItems(n: number): FlatItem[] {
  const statuses: FlatItem['status'][] = ['open', 'closed', 'merged'];
  return Array.from({ length: n }, (_, i) => ({
    id: `item-${i}`,
    title: `PR #${i + 1}: Add feature ${i + 1}`,
    subtitle: `opened by user-${(i % 5) + 1} · ${i + 1} comments`,
    status: statuses[i % 3] as FlatItem['status'],
  }));
}

function ItemRow({
  item,
  isLast,
  selected,
  onClick,
}: {
  item: FlatItem;
  isLast: boolean;
  selected?: boolean;
  onClick?: (e: React.MouseEvent) => void;
}) {
  return (
    <ListView.Row interactive isLast={isLast} selected={selected} onClick={onClick}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          backgroundColor: STATUS_COLOR[item.status],
          flexShrink: 0,
          marginTop: 4,
        }}
      />
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: 'var(--em-text-sm)',
            fontWeight: 400,
            color: 'var(--em-foreground)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {item.title}
        </div>
        <div
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-muted)',
            marginTop: 2,
          }}
        >
          {item.subtitle}
        </div>
      </div>
    </ListView.Row>
  );
}

// ── 1. Basic flat list ────────────────────────────────────────────────────────

const FLAT_1000 = makeFlatItems(1000);

export const FlatList: Story = {
  name: 'Flat list (1 000 items)',
  render: () => (
    <div className={s.w96} style={{ height: '32rem', display: 'flex', flexDirection: 'column' }}>
      <ListView>
        <ListView.Body>
          <ListView.List
            items={FLAT_1000}
            getItemKey={(item) => item.id}
            renderItem={(item, i) => (
              <ItemRow key={item.id} item={item} isLast={i === FLAT_1000.length - 1} />
            )}
          />
        </ListView.Body>
      </ListView>
    </div>
  ),
};

// ── 2. Infinite scroll ────────────────────────────────────────────────────────

function InfiniteScrollDemo() {
  const [items, setItems] = React.useState<FlatItem[]>(() => makeFlatItems(30));
  const [isFetchingMore, setIsFetchingMore] = React.useState(false);
  const [hasMore, setHasMore] = React.useState(true);

  function handleEndReached() {
    if (isFetchingMore || !hasMore) return;
    setIsFetchingMore(true);
    setTimeout(() => {
      setItems((prev) => {
        const next = [
          ...prev,
          ...makeFlatItems(20).map((it, i) => ({ ...it, id: `item-${prev.length + i}` })),
        ];
        if (next.length >= 150) setHasMore(false);
        return next;
      });
      setIsFetchingMore(false);
    }, 800);
  }

  return (
    <div className={s.w96} style={{ height: '32rem', display: 'flex', flexDirection: 'column' }}>
      <ListView>
        <ListView.Body>
          <ListView.List
            items={items}
            getItemKey={(item) => item.id}
            renderItem={(item, i) => (
              <ItemRow key={item.id} item={item} isLast={i === items.length - 1} />
            )}
            onEndReached={handleEndReached}
            isFetchingMore={isFetchingMore}
          />
        </ListView.Body>
      </ListView>
    </div>
  );
}

export const InfiniteScroll: Story = {
  name: 'Infinite scroll',
  render: () => <InfiniteScrollDemo />,
};

// ── 3. State slots ────────────────────────────────────────────────────────────

export const LoadingSlot: Story = {
  name: 'Loading slot',
  render: () => (
    <div className={s.w96} style={{ height: '20rem', display: 'flex', flexDirection: 'column' }}>
      <ListView>
        <ListView.Body>
          <ListView.List
            items={[]}
            isLoading
            loadingSlot={
              <div
                style={{
                  padding: '2rem',
                  textAlign: 'center',
                  color: 'var(--em-foreground-muted)',
                  fontSize: 'var(--em-text-sm)',
                }}
              >
                Loading pull requests…
              </div>
            }
            getItemKey={(x: never) => x}
            renderItem={(x: never) => x}
          />
        </ListView.Body>
      </ListView>
    </div>
  ),
};

export const EmptySlot: Story = {
  name: 'Empty slot',
  render: () => (
    <div className={s.w96} style={{ height: '20rem', display: 'flex', flexDirection: 'column' }}>
      <ListView>
        <ListView.Body>
          <ListView.List
            items={[]}
            emptySlot={
              <div
                style={{
                  padding: '2rem',
                  textAlign: 'center',
                  color: 'var(--em-foreground-muted)',
                  fontSize: 'var(--em-text-sm)',
                }}
              >
                <LayoutListIcon
                  style={{ width: 32, height: 32, margin: '0 auto 0.5rem', opacity: 0.4 }}
                />
                <p>No pull requests match your filters.</p>
              </div>
            }
            getItemKey={(x: never) => x}
            renderItem={(x: never) => x}
          />
        </ListView.Body>
      </ListView>
    </div>
  ),
};

export const ErrorSlot: Story = {
  name: 'Error slot',
  render: () => (
    <div className={s.w96} style={{ height: '20rem', display: 'flex', flexDirection: 'column' }}>
      <ListView>
        <ListView.Body>
          <ListView.List
            items={undefined}
            errorSlot={
              <div
                style={{
                  padding: '2rem',
                  textAlign: 'center',
                  color: 'var(--em-foreground-muted)',
                  fontSize: 'var(--em-text-sm)',
                }}
              >
                <p style={{ color: 'var(--em-status-error)' }}>Failed to load items.</p>
              </div>
            }
            getItemKey={(x: never) => x}
            renderItem={(x: never) => x}
          />
        </ListView.Body>
      </ListView>
    </div>
  ),
};

// ── 4. Full ListView with Toolbar + FilterPills ───────────────────────────────

const ALL_ITEMS = makeFlatItems(200);

function FullListViewDemo() {
  const [query, setQuery] = React.useState('');
  const [status, setStatus] = React.useState<string>('all');
  const [activeAuthor, setActiveAuthor] = React.useState<string | null>(null);

  const filtered = ALL_ITEMS.filter(
    (it) =>
      (status === 'all' || it.status === status) &&
      (!activeAuthor || it.subtitle.includes(activeAuthor)) &&
      it.title.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className={s.w96} style={{ height: '36rem', display: 'flex', flexDirection: 'column' }}>
      <ListView>
        <ListView.Toolbar>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Tabs.Root value={status} onValueChange={(v) => setStatus(v ?? 'all')}>
              <Tabs.List>
                <Tabs.Tab value="all">All</Tabs.Tab>
                <Tabs.Tab value="open">Open</Tabs.Tab>
                <Tabs.Tab value="closed">Closed</Tabs.Tab>
                <Tabs.Tab value="merged">Merged</Tabs.Tab>
              </Tabs.List>
            </Tabs.Root>
            <SearchInput
              size="sm"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onClear={() => setQuery('')}
              placeholder="Search PRs…"
              style={{ flex: 1, minWidth: 0 }}
            />
          </div>
          <ListView.FilterPills>
            {activeAuthor && (
              <ListView.FilterPill label={activeAuthor} onRemove={() => setActiveAuthor(null)} />
            )}
          </ListView.FilterPills>
          <div
            style={{
              display: 'flex',
              gap: '0.375rem',
              fontSize: 'var(--em-text-xs)',
              color: 'var(--em-foreground-muted)',
            }}
          >
            <ListView.FilterButton
              icon={<FilterIcon />}
              active={activeAuthor === 'user-1'}
              onClick={() => setActiveAuthor((prev) => (prev === 'user-1' ? null : 'user-1'))}
            >
              Author: user-1
            </ListView.FilterButton>
          </div>
        </ListView.Toolbar>
        <ListView.Body>
          <ListView.List
            items={filtered}
            getItemKey={(item) => item.id}
            renderItem={(item, i) => (
              <ItemRow key={item.id} item={item} isLast={i === filtered.length - 1} />
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
    </div>
  );
}

export const WithToolbar: Story = {
  name: 'With Toolbar + FilterPills',
  render: () => <FullListViewDemo />,
};

// ── 5. Multi-select + Footer ──────────────────────────────────────────────────

const SELECT_ITEMS = makeFlatItems(50);

function MultiSelectDemo() {
  const sel = ListView.useSelection(SELECT_ITEMS.map((i) => i.id));

  return (
    <div
      className={s.w96}
      style={{ height: '28rem', display: 'flex', flexDirection: 'column', position: 'relative' }}
    >
      <ListView>
        <ListView.Toolbar>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              type="button"
              onClick={sel.count === SELECT_ITEMS.length ? sel.clear : sel.selectAll}
              style={{
                fontSize: 'var(--em-text-xs)',
                color: 'var(--em-foreground-muted)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
              }}
            >
              <CheckIcon style={{ width: '0.875rem', height: '0.875rem' }} />
              {sel.count === SELECT_ITEMS.length ? 'Deselect all' : 'Select all'}
            </button>
            {sel.count > 0 && (
              <span style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)' }}>
                {sel.count} selected
              </span>
            )}
          </div>
        </ListView.Toolbar>
        <ListView.Body>
          <ListView.List
            items={SELECT_ITEMS}
            getItemKey={(item) => item.id}
            renderItem={(item, i) => (
              <ItemRow
                key={item.id}
                item={item}
                isLast={i === SELECT_ITEMS.length - 1}
                selected={sel.isSelected(item.id)}
                onClick={(e) => sel.toggle(item.id, e)}
              />
            )}
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
                backdropFilter: 'blur(4px)',
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
    </div>
  );
}

export const MultiSelect: Story = {
  name: 'Multi-select + Footer bar',
  render: () => <MultiSelectDemo />,
};

// ── 6. Grouped/sectioned — Agents view ───────────────────────────────────────

interface AgentItem {
  id: string;
  name: string;
  description: string;
  installed: boolean;
  icon: React.ReactNode;
}

const AGENT_ITEMS: AgentItem[] = [
  {
    id: 'claude',
    name: 'Claude (Sonnet)',
    description: "Anthropic's flagship coding agent",
    installed: true,
    icon: <TerminalIcon style={{ width: 16, height: 16 }} />,
  },
  {
    id: 'codex',
    name: 'OpenAI Codex',
    description: 'Code generation from OpenAI',
    installed: true,
    icon: <PackageIcon style={{ width: 16, height: 16 }} />,
  },
  {
    id: 'gemini',
    name: 'Gemini Code',
    description: "Google's AI coding assistant",
    installed: false,
    icon: <GlobeIcon style={{ width: 16, height: 16 }} />,
  },
  {
    id: 'aider',
    name: 'Aider',
    description: 'AI pair programmer in your terminal',
    installed: false,
    icon: <TerminalIcon style={{ width: 16, height: 16 }} />,
  },
  {
    id: 'copilot',
    name: 'GitHub Copilot',
    description: 'AI coding suggestions from GitHub',
    installed: true,
    icon: <PackageIcon style={{ width: 16, height: 16 }} />,
  },
  {
    id: 'cursor-agent',
    name: 'Cursor Agent',
    description: "Cursor's built-in agent mode",
    installed: true,
    icon: <GlobeIcon style={{ width: 16, height: 16 }} />,
  },
  {
    id: 'devin',
    name: 'Devin',
    description: 'Autonomous AI software engineer',
    installed: false,
    icon: <TerminalIcon style={{ width: 16, height: 16 }} />,
  },
  {
    id: 'mentat',
    name: 'Mentat',
    description: 'Code-editing AI assistant',
    installed: false,
    icon: <PackageIcon style={{ width: 16, height: 16 }} />,
  },
];

const RECOMMENDED_IDS = new Set(['claude', 'codex', 'copilot']);

function AgentRow({ agent, isLast }: { agent: AgentItem; isLast: boolean }) {
  return (
    <ListView.Row interactive isLast={isLast}>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 'var(--em-radius-md)',
          backgroundColor: 'var(--em-surface-hover)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          color: 'var(--em-foreground-muted)',
        }}
      >
        {agent.icon}
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          style={{ fontSize: 'var(--em-text-sm)', fontWeight: 400, color: 'var(--em-foreground)' }}
        >
          {agent.name}
        </div>
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
      {agent.installed && (
        <span
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-status-success)',
            flexShrink: 0,
            alignSelf: 'center',
          }}
        >
          Installed
        </span>
      )}
    </ListView.Row>
  );
}

function AgentsViewDemo() {
  const [filter, setFilter] = React.useState<'all' | 'installed' | 'not-installed'>('all');
  const [query, setQuery] = React.useState('');

  const visible = AGENT_ITEMS.filter(
    (a) =>
      (filter === 'all' || (filter === 'installed' ? a.installed : !a.installed)) &&
      a.name.toLowerCase().includes(query.toLowerCase())
  );

  const recommended = visible.filter((a) => RECOMMENDED_IDS.has(a.id));
  const rest = visible.filter((a) => !RECOMMENDED_IDS.has(a.id));

  const sections = [
    ...(recommended.length > 0
      ? [
          {
            key: 'recommended',
            header: <ListView.SectionHeader label="Recommended" count={recommended.length} />,
            items: recommended,
          },
        ]
      : []),
    ...(rest.length > 0
      ? [
          {
            key: 'all',
            header: <ListView.SectionHeader label="All agents" count={rest.length} />,
            items: rest,
          },
        ]
      : []),
  ];

  return (
    <div className={s.w96} style={{ height: '40rem', display: 'flex', flexDirection: 'column' }}>
      <ListView>
        <ListView.Toolbar>
          <Tabs.Root value={filter} onValueChange={(v) => setFilter((v ?? 'all') as typeof filter)}>
            <Tabs.List>
              <Tabs.Tab value="all">All</Tabs.Tab>
              <Tabs.Tab value="installed">Installed</Tabs.Tab>
              <Tabs.Tab value="not-installed">Not installed</Tabs.Tab>
            </Tabs.List>
          </Tabs.Root>
          <SearchInput
            size="sm"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onClear={() => setQuery('')}
            placeholder="Search agents…"
          />
        </ListView.Toolbar>
        <ListView.Body>
          <ListView.List
            sections={sections}
            getItemKey={(agent) => agent.id}
            renderItem={(agent, i) => (
              <AgentRow key={agent.id} agent={agent} isLast={i === visible.length - 1} />
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
    </div>
  );
}

export const AgentsView: Story = {
  name: 'Grouped sections — Agents view',
  render: () => <AgentsViewDemo />,
};
