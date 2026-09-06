import type { Meta, StoryObj } from '@storybook/react-vite';
import { Fragment, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { useSyncExternalStore } from 'react';
import {
  Resizable,
  useCollapsiblePanelBinding,
  useResizableDefaultLayout,
  type LayoutStorage,
} from '.';

const meta: Meta = {
  title: 'Primitives/Resizable/PanelBinding',
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj;

// ---------------------------------------------------------------------------
// Story-local storage stub + inspector, standing in for the app's memento
// facade. Logs every setItem and every getItem whose observed value changed
// (raw getItem calls happen on every render, so repeats are suppressed to
// keep the log readable).
// ---------------------------------------------------------------------------

type Layout = Record<string, number>;

interface StorageLogEntry {
  seq: number;
  op: 'getItem' | 'setItem';
  key: string;
  value: string | null;
}

class LoggingMemoryStorage implements LayoutStorage {
  private map = new Map<string, string>();
  private entries: StorageLogEntry[] = [];
  private lastReadValue = new Map<string, string | null>();
  private listeners = new Set<() => void>();
  private seq = 0;
  private notifyQueued = false;

  getItem = (key: string): string | null => {
    const value = this.map.get(key) ?? null;
    if (this.lastReadValue.get(key) !== value || !this.lastReadValue.has(key)) {
      this.lastReadValue.set(key, value);
      this.push({ seq: ++this.seq, op: 'getItem', key, value });
    }
    return value;
  };

  setItem = (key: string, value: string): void => {
    this.map.set(key, value);
    this.push({ seq: ++this.seq, op: 'setItem', key, value });
  };

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): StorageLogEntry[] => this.entries;

  private push(entry: StorageLogEntry) {
    // Cap and copy so getSnapshot returns a fresh reference per change.
    this.entries = [...this.entries.slice(-19), entry];
    // getItem is called during render; notifying listeners synchronously would
    // trigger setState-during-render warnings, so defer to a microtask.
    if (!this.notifyQueued) {
      this.notifyQueued = true;
      queueMicrotask(() => {
        this.notifyQueued = false;
        for (const listener of this.listeners) listener();
      });
    }
  }
}

function useLoggingMemoryStorage(): LoggingMemoryStorage {
  const [storage] = useState(() => new LoggingMemoryStorage());
  return storage;
}

const mono: CSSProperties = {
  fontFamily: 'var(--em-font-mono, monospace)',
  fontSize: '0.7rem',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
  margin: 0,
};

function Frame({ children, height = 360 }: { children: ReactNode; height?: number }) {
  return (
    <div style={{ flex: 1, height, border: '1px solid var(--em-border)', minWidth: 0 }}>
      {children}
    </div>
  );
}

function StateInspector({
  semantic,
  lastLayout,
  storage,
}: {
  semantic: Record<string, unknown>;
  lastLayout: Layout | null;
  storage: LoggingMemoryStorage;
}) {
  const log = useSyncExternalStore(storage.subscribe, storage.getSnapshot);
  return (
    <div
      style={{
        width: 340,
        flexShrink: 0,
        border: '1px dashed var(--em-border)',
        padding: 8,
        overflow: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div>
        <strong style={{ fontSize: '0.75rem' }}>semantic state</strong>
        <pre style={mono}>{JSON.stringify(semantic, null, 2)}</pre>
      </div>
      <div>
        <strong style={{ fontSize: '0.75rem' }}>last onLayoutChanged</strong>
        <pre style={mono}>{lastLayout ? JSON.stringify(lastLayout, null, 2) : '(none yet)'}</pre>
      </div>
      <div style={{ minHeight: 0 }}>
        <strong style={{ fontSize: '0.75rem' }}>
          storage log (setItem + changed getItem only)
        </strong>
        <pre style={mono}>
          {log.length === 0
            ? '(empty)'
            : log
                .map(
                  (e) =>
                    `#${e.seq} ${e.op} ${e.key.replace('react-resizable-panels:', '…:')}\n    ${e.value}`
                )
                .join('\n')}
        </pre>
      </div>
    </div>
  );
}

function Filler({ label }: { label: string }) {
  return (
    <div
      style={{
        display: 'flex',
        height: '100%',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '0.8rem',
        color: 'var(--em-foreground-muted)',
        overflow: 'hidden',
      }}
    >
      {label}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Story 1: CollapsibleSidebar (horizontal group + the shared binding hook).
// Demonstrates drag persistence at pointer-up, threshold drag-to-close without
// sliver persistence, and reopen restoring the last good size.
// ---------------------------------------------------------------------------

function CollapsibleSidebarDemo() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [lastLayout, setLastLayout] = useState<Layout | null>(null);
  const storage = useLoggingMemoryStorage();

  const binding = useCollapsiblePanelBinding({
    storageKey: 'story-binding-sidebar',
    storage,
    panelIds: ['main', 'sidebar'],
    collapsiblePanelId: 'sidebar',
    open: sidebarOpen,
    onCloseRequest: () => setSidebarOpen(false),
    closeThreshold: 8,
  });

  return (
    <div style={{ display: 'flex', gap: 12 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ marginBottom: 8 }}>
          <button type="button" onClick={() => setSidebarOpen((v) => !v)}>
            {sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          </button>{' '}
          <span style={{ fontSize: '0.75rem', color: 'var(--em-foreground-muted)' }}>
            drag the handle far right to close via threshold; reopen restores last width
          </span>
        </div>
        <Frame>
          <Resizable.Group
            orientation="horizontal"
            id="story-binding-sidebar-group"
            defaultLayout={binding.groupProps.defaultLayout}
            onLayoutChanged={(layout) => {
              setLastLayout(layout);
              binding.groupProps.onLayoutChanged(layout);
            }}
          >
            <Resizable.Panel id="main" minSize="30%">
              <Filler label="Main content (never remounts)" />
            </Resizable.Panel>
            {/* Closed = panel AND handle unmount. No collapse()/resize() calls. */}
            {sidebarOpen && (
              <>
                <Resizable.Handle />
                {/* id comes from the binding (generation-suffixed after a threshold close). */}
                <Resizable.Panel maxSize="60%" {...binding.collapsiblePanelProps}>
                  <Filler label="Sidebar" />
                </Resizable.Panel>
              </>
            )}
          </Resizable.Group>
        </Frame>
      </div>
      <StateInspector semantic={{ sidebarOpen }} lastLayout={lastLayout} storage={storage} />
    </div>
  );
}

export const CollapsibleSidebar: Story = {
  render: () => <CollapsibleSidebarDemo />,
};

// ---------------------------------------------------------------------------
// Story 2: TerminalDrawer (the vertical case via the same binding hook).
// ---------------------------------------------------------------------------

function TerminalDrawerDemo() {
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [lastLayout, setLastLayout] = useState<Layout | null>(null);
  const storage = useLoggingMemoryStorage();

  const binding = useCollapsiblePanelBinding({
    storageKey: 'story-binding-drawer',
    storage,
    panelIds: ['content', 'drawer'],
    collapsiblePanelId: 'drawer',
    open: drawerOpen,
    onCloseRequest: () => setDrawerOpen(false),
    closeThreshold: 8,
  });

  return (
    <div style={{ display: 'flex', gap: 12 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ marginBottom: 8 }}>
          <button type="button" onClick={() => setDrawerOpen((v) => !v)}>
            {drawerOpen ? 'Close drawer' : 'Open drawer'}
          </button>{' '}
          <span style={{ fontSize: '0.75rem', color: 'var(--em-foreground-muted)' }}>
            drag the handle to the bottom edge to close via threshold
          </span>
        </div>
        <Frame>
          <Resizable.Group
            orientation="vertical"
            id="story-binding-drawer-group"
            defaultLayout={binding.groupProps.defaultLayout}
            onLayoutChanged={(layout) => {
              setLastLayout(layout);
              binding.groupProps.onLayoutChanged(layout);
            }}
          >
            <Resizable.Panel id="content" minSize="30%">
              <Filler label="Editor content" />
            </Resizable.Panel>
            {drawerOpen && (
              <>
                <Resizable.Handle />
                <Resizable.Panel maxSize="70%" {...binding.collapsiblePanelProps}>
                  <Filler label="Terminal drawer" />
                </Resizable.Panel>
              </>
            )}
          </Resizable.Group>
        </Frame>
      </div>
      <StateInspector semantic={{ drawerOpen }} lastLayout={lastLayout} storage={storage} />
    </div>
  );
}

export const TerminalDrawer: Story = {
  render: () => <TerminalDrawerDemo />,
};

// ---------------------------------------------------------------------------
// Story 3: SectionedPanel — the multi-section composition (changes-panel
// shape). Headers are always-visible inert rows; only expanded bodies are
// panels. This surface stays a per-feature composition (no drag-to-close),
// reusing the storage plumbing: one `useResizableDefaultLayout` whose
// `panelIds` are the currently expanded section ids, so the library natively
// keys storage per expansion combination.
//
// `defaultLayout` is only consulted at GROUP mount, so the Group is keyed by
// the combination and remounts on any toggle — accepted cost: sibling
// expanded bodies remount too.
// ---------------------------------------------------------------------------

const SECTIONS = [
  { id: 'changes', label: 'Changes' },
  { id: 'commits', label: 'Commits' },
  { id: 'pr', label: 'Pull Request' },
] as const;
type SectionId = (typeof SECTIONS)[number]['id'];

function SectionHeader({
  label,
  expanded,
  onToggle,
}: {
  label: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    // Inert direct child of the Group: fixed height, no flex-grow. The library
    // ignores it for layout math, same as it does for separators.
    <div
      style={{
        flex: '0 0 auto',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        height: 26,
        padding: '0 8px',
        fontSize: '0.72rem',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        cursor: 'pointer',
        userSelect: 'none',
        background: 'var(--em-surface, var(--em-background))',
        borderTop: '1px solid var(--em-border)',
      }}
      onClick={onToggle}
    >
      <span style={{ width: 10, display: 'inline-block' }}>{expanded ? '▾' : '▸'}</span>
      {label}
    </div>
  );
}

function SectionedPanelDemo() {
  const [expanded, setExpanded] = useState<Record<SectionId, boolean>>({
    changes: true,
    commits: true,
    pr: false,
  });
  const [lastLayout, setLastLayout] = useState<Layout | null>(null);
  const storage = useLoggingMemoryStorage();

  const expandedIds = SECTIONS.filter((s) => expanded[s.id]).map((s) => s.id);

  const { defaultLayout, onLayoutChanged: persist } = useResizableDefaultLayout({
    id: 'story-binding-sections',
    panelIds: expandedIds,
    storage,
  });

  const onLayoutChanged = (layout: Layout) => {
    setLastLayout(layout);
    // No drag-to-close for sections: headers are the only collapse affordance,
    // and body minSize prevents dragging a section to nothing.
    persist(layout);
  };

  const toggle = (id: SectionId) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  return (
    <div style={{ display: 'flex', gap: 12 }}>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', gap: 0, height: 420 }}>
        <div style={{ width: 260, borderRight: '1px solid var(--em-border)', height: '100%' }}>
          <Resizable.Group
            orientation="vertical"
            id="story-binding-sections-group"
            // Remount the group per expansion combination so the freshly-read
            // per-combination defaultLayout is applied (see block comment).
            key={expandedIds.join('|')}
            defaultLayout={defaultLayout}
            onLayoutChanged={onLayoutChanged}
            style={{ height: '100%' }}
          >
            {SECTIONS.map((section, index) => {
              const isExpanded = expanded[section.id];
              const hasLaterExpanded = SECTIONS.slice(index + 1).some((s) => expanded[s.id]);
              return (
                // Fragments don't create DOM nodes, so Panels/Separators stay
                // direct DOM children of the Group as the library requires.
                <Fragment key={section.id}>
                  <SectionHeader
                    label={section.label}
                    expanded={isExpanded}
                    onToggle={() => toggle(section.id)}
                  />
                  {isExpanded && (
                    <Resizable.Panel id={section.id} minSize="48px">
                      <div style={{ height: '100%', overflow: 'auto' }}>
                        <Filler label={`${section.label} body`} />
                      </div>
                    </Resizable.Panel>
                  )}
                  {isExpanded && hasLaterExpanded && <Resizable.Handle />}
                </Fragment>
              );
            })}
          </Resizable.Group>
        </div>
        <div style={{ flex: 1, border: '1px solid var(--em-border)', borderLeft: 'none' }}>
          <Filler label="Main area" />
        </div>
      </div>
      <StateInspector semantic={{ expanded }} lastLayout={lastLayout} storage={storage} />
    </div>
  );
}

export const SectionedPanel: Story = {
  render: () => <SectionedPanelDemo />,
};
