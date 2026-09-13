import type { Meta, StoryObj } from '@storybook/react-vite';
import { PlusIcon, WrenchIcon } from 'lucide-react';
import * as React from 'react';
import { Button } from '../../primitives/button';
import { SearchInput } from '../../primitives/search-input';
import { PageLayout, type PageNavItem, type PageSidebarMenuItem } from './index';

const meta: Meta = {
  title: 'Patterns/PageLayout',
  parameters: { layout: 'fullscreen' },
};
export default meta;
type Story = StoryObj;

// ── Placeholder helpers ───────────────────────────────────────────────────────

function Card({ title, rows = 3 }: { title: string; rows?: number }) {
  return (
    <div
      style={{
        border: '1px solid var(--em-border)',
        borderRadius: 'var(--em-radius-lg)',
        padding: '1rem 1.25rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
      }}
    >
      <div
        style={{ fontSize: 'var(--em-text-sm)', fontWeight: 400, color: 'var(--em-foreground)' }}
      >
        {title}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          style={{
            height: '0.75rem',
            borderRadius: '999px',
            backgroundColor: 'var(--em-background-2)',
            width: `${65 + (i % 3) * 10}%`,
          }}
        />
      ))}
    </div>
  );
}

function PlaceholderList({ count = 5 }: { count?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {Array.from({ length: count }).map((_, i) => (
        <Card key={i} title={`Item ${i + 1}`} />
      ))}
    </div>
  );
}

// ── 1. Library style — sidebar + content (max-w-3xl) ─────────────────────────

const LIBRARY_ITEMS = [
  { id: 'prompts', label: 'Prompts', icon: 'book-open' },
  { id: 'skills', label: 'Skills', icon: 'wrench' },
  { id: 'mcp', label: 'MCP', icon: 'terminal' },
] satisfies PageNavItem[];

function LibraryDemo() {
  const [tab, setTab] = React.useState('prompts');
  const [query, setQuery] = React.useState('');

  return (
    <div style={{ height: '40rem', display: 'flex', flexDirection: 'column' }}>
      <PageLayout
        sidebar={
          <PageLayout.SidebarMenu
            items={LIBRARY_ITEMS}
            activeId={tab}
            onSelect={(item) => setTab(item.id)}
          />
        }
      >
        <PageLayout.Content maxWidth="3xl">
          <PageLayout.Header
            title={LIBRARY_ITEMS.find((i) => i.id === tab)?.label ?? ''}
            description="Manage reusable prompts that can be sent from task prompt menus."
            sticky
            actions={
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '0.5rem',
                }}
              >
                <SearchInput
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onClear={() => setQuery('')}
                  placeholder="Search…"
                  style={{ flex: 1 }}
                />
                <Button size="xs">
                  <PlusIcon size={14} />
                  New Prompt
                </Button>
              </div>
            }
          />
          <div style={{ paddingTop: '1.5rem', paddingBottom: '2.5rem' }}>
            <PlaceholderList count={6} />
          </div>
        </PageLayout.Content>
      </PageLayout>
    </div>
  );
}

export const LibraryStyle: Story = {
  name: 'Library style — sidebar + content (max-w-3xl)',
  render: () => <LibraryDemo />,
};

// ── 2. Settings style — sidebar + content (default max-w-4xl) ────────────────

const SETTINGS_ITEMS = [
  { id: 'general', label: 'General', icon: 'settings' },
  { id: 'account', label: 'Account', icon: 'user' },
  { id: 'agents', label: 'Agents', icon: 'bot' },
  {
    id: 'integrations',
    label: 'Integrations',
    icon: 'globe',
  },
  { id: 'connections', label: 'Connections', icon: 'zap' },
  {
    id: 'docs',
    label: 'Docs',
    icon: 'external-link',
    isExternal: true,
  },
] satisfies PageNavItem[];

function SettingsDemo() {
  const [tab, setTab] = React.useState('general');

  return (
    <div
      style={{
        height: '40rem',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--em-background)',
      }}
    >
      <PageLayout
        sidebar={
          <PageLayout.SidebarMenu
            items={SETTINGS_ITEMS}
            activeId={tab}
            onSelect={(item) => {
              if (!item.isExternal) setTab(item.id);
            }}
          />
        }
      >
        <PageLayout.Content>
          <div
            style={{
              paddingBottom: '2.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '2rem',
            }}
          >
            <PageLayout.Header
              title={SETTINGS_ITEMS.find((i) => i.id === tab)?.label ?? ''}
              description="Manage your account, privacy settings, notifications, and app updates."
              sticky
            />
            <Card title="Update settings" rows={4} />
            <Card title="Telemetry" rows={2} />
            <Card title="Auto-approve defaults" rows={3} />
            <Card title="Appearance" rows={2} />
          </div>
        </PageLayout.Content>
      </PageLayout>
    </div>
  );
}

export const SettingsStyle: Story = {
  name: 'Settings style — sidebar + content (max-w-4xl)',
  render: () => <SettingsDemo />,
};

// ── 3. Automations style — content-only, no sidebar ──────────────────────────

function AutomationsDemo() {
  const [query, setQuery] = React.useState('');

  return (
    <div style={{ height: '40rem', display: 'flex', flexDirection: 'column' }}>
      <PageLayout>
        <PageLayout.Content>
          <div
            style={{
              paddingTop: '1.5rem',
              paddingBottom: '2.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.5rem',
            }}
          >
            <PageLayout.Header
              title="Automations"
              description="Run agents on a schedule across your projects."
              actions={
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '0.5rem',
                  }}
                >
                  <SearchInput
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onClear={() => setQuery('')}
                    placeholder="Search automations…"
                    style={{ flex: 1 }}
                  />
                  <Button size="xs" style={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
                    <PlusIcon style={{ width: '0.875rem', height: '0.875rem' }} />
                    New Automation
                  </Button>
                </div>
              }
            />
            <PlaceholderList count={4} />
          </div>
        </PageLayout.Content>
      </PageLayout>
    </div>
  );
}

export const AutomationsStyle: Story = {
  name: 'Automations style — content-only',
  render: () => <AutomationsDemo />,
};

// ── 4. Custom sidebar — PageLayout.Sidebar bare slot ─────────────────────────

function CustomSidebarDemo() {
  const [selected, setSelected] = React.useState(0);
  const projects = ['emdash', 'api-gateway', 'frontend', 'docs-site'];

  return (
    <div style={{ height: '40rem', display: 'flex', flexDirection: 'column' }}>
      <PageLayout
        sidebar={
          <PageLayout.Sidebar>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <p
                style={{
                  fontSize: 'var(--em-text-xs)',
                  fontWeight: 400,
                  color: 'var(--em-foreground-muted)',
                  paddingLeft: '0.75rem',
                  paddingBottom: '0.25rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                Projects
              </p>
              {projects.map((name, i) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => setSelected(i)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    width: '100%',
                    border: 'none',
                    borderRadius: 'var(--em-radius-md)',
                    padding: '0.5rem 0.75rem',
                    fontSize: 'var(--em-text-sm)',
                    cursor: 'pointer',
                    backgroundColor: selected === i ? 'var(--em-background-2)' : 'transparent',
                    color: selected === i ? 'var(--em-foreground)' : 'var(--em-foreground-muted)',
                    textAlign: 'left',
                  }}
                >
                  <WrenchIcon style={{ width: 14, height: 14, flexShrink: 0 }} />
                  {name}
                </button>
              ))}
            </div>
          </PageLayout.Sidebar>
        }
      >
        <PageLayout.Content>
          <div
            style={{
              paddingBottom: '2.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.5rem',
            }}
          >
            <PageLayout.Header
              title={projects[selected] ?? ''}
              description="Custom sidebar demonstrating the bare PageLayout.Sidebar slot."
              sticky
            />
            <PlaceholderList count={3} />
          </div>
        </PageLayout.Content>
      </PageLayout>
    </div>
  );
}

export const CustomSidebar: Story = {
  name: 'Custom sidebar — PageLayout.Sidebar bare slot',
  render: () => <CustomSidebarDemo />,
};

// ── 5. Sectioned sidebar — PageNavSection labels ──────────────────────────────

const SECTIONED_ITEMS = [
  { kind: 'section', id: 'account-section', label: 'Account' },
  { id: 'general', label: 'General', icon: 'settings' },
  { id: 'account', label: 'Account', icon: 'user' },
  { id: 'integrations', label: 'Integrations', icon: 'plug' },
  { kind: 'section', id: 'application-section', label: 'Application' },
  { id: 'interface', label: 'Interface', icon: 'panel-left' },
  { id: 'browser', label: 'Browser', icon: 'globe' },
  { id: 'repository', label: 'Repository', icon: 'git-branch' },
  { kind: 'section', id: 'workspace-section', label: 'Workspace' },
  { id: 'agents', label: 'Agents', icon: 'bot' },
  { id: 'workspaces', label: 'Workspaces (local)', icon: 'folder-git-2' },
  { kind: 'section', id: 'remote-section', label: 'Remote' },
  { id: 'remote-machines', label: 'Remote Machines', icon: 'server' },
  { kind: 'divider' } satisfies PageSidebarMenuItem,
  { id: 'docs', label: 'Docs', icon: 'external-link', isExternal: true },
] satisfies PageSidebarMenuItem[];

function SectionedSidebarDemo() {
  const [tab, setTab] = React.useState('general');

  return (
    <div
      style={{
        height: '40rem',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--em-background)',
      }}
    >
      <PageLayout
        sidebar={
          <PageLayout.SidebarMenu
            items={SECTIONED_ITEMS}
            activeId={tab}
            onSelect={(item) => {
              if (!item.isExternal) setTab(item.id);
            }}
          />
        }
      >
        <PageLayout.Content>
          <PageLayout.Header
            title={
              SECTIONED_ITEMS.find(
                (item) => item.kind !== 'divider' && item.kind !== 'section' && item.id === tab
              )?.label ?? ''
            }
            description="Sectioned sidebar demonstrating section label support."
            sticky
          />
          <div style={{ paddingTop: '1.5rem', paddingBottom: '2.5rem' }}>
            <PlaceholderList count={4} />
          </div>
        </PageLayout.Content>
      </PageLayout>
    </div>
  );
}

export const SectionedSidebar: Story = {
  name: 'Sectioned sidebar — section labels',
  render: () => <SectionedSidebarDemo />,
};

// ── 6. Sidebar with footer — pinned slots + scrolling nav ─────────────────────

const SIDEBAR_WITH_FOOTER_ITEMS: PageSidebarMenuItem[] = [
  { kind: 'section', id: 'projects-section', label: 'Projects' },
  ...Array.from(
    { length: 20 },
    (_, index) =>
      ({
        id: `project-${index + 1}`,
        label: `Project ${index + 1}`,
        icon: 'folder',
        badge: String(index + 2),
      }) satisfies PageNavItem
  ),
  { kind: 'divider' },
  { kind: 'section', id: 'resources-section', label: 'Resources' },
  { id: 'templates', label: 'Templates', icon: 'sparkles' },
  { id: 'archive', label: 'Archive', icon: 'archive' },
];

function SidebarWithFooterDemo() {
  const [tab, setTab] = React.useState('project-1');
  const [query, setQuery] = React.useState('');

  return (
    <div
      style={{
        height: '40rem',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--em-background)',
      }}
    >
      <PageLayout
        sidebar={
          <PageLayout.SidebarMenu
            items={SIDEBAR_WITH_FOOTER_ITEMS}
            activeId={tab}
            onSelect={(item) => setTab(item.id)}
            header={
              <SearchInput
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onClear={() => setQuery('')}
                placeholder="Search projects…"
              />
            }
            footer={
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.5rem',
                  borderTop: '1px solid var(--em-border)',
                  paddingTop: '0.75rem',
                }}
              >
                <div
                  style={{
                    color: 'var(--em-foreground-passive)',
                    fontSize: 'var(--em-text-xs)',
                    paddingLeft: '0.75rem',
                    paddingRight: '0.75rem',
                  }}
                >
                  Emdash UI v1.0.0
                </div>
                <Button size="xs" variant="ghost" style={{ justifyContent: 'flex-start' }}>
                  Manage sidebar
                </Button>
              </div>
            }
          />
        }
      >
        <PageLayout.Content>
          <PageLayout.Header
            title={
              SIDEBAR_WITH_FOOTER_ITEMS.find(
                (item) => item.kind !== 'divider' && item.kind !== 'section' && item.id === tab
              )?.label ?? ''
            }
            description="Long sidebar demonstrating pinned header/footer slots and a scrolling nav."
            sticky
          />
          <div style={{ paddingTop: '1.5rem', paddingBottom: '2.5rem' }}>
            <PlaceholderList count={4} />
          </div>
        </PageLayout.Content>
      </PageLayout>
    </div>
  );
}

export const SidebarWithFooter: Story = {
  name: 'Sidebar with footer — scrolling nav',
  render: () => <SidebarWithFooterDemo />,
};
