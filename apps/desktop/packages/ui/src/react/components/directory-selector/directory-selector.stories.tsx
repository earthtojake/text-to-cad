import type { Meta, StoryObj } from '@storybook/react-vite';
import * as React from 'react';
import {
  DirectorySelector,
  type DirectoryEntry,
  type DirectoryListing,
} from './directory-selector';
import { useDirectoryHistory } from './use-directory-history';

const meta: Meta<typeof DirectorySelector> = {
  title: 'Components/DirectorySelector',
  component: DirectorySelector,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof DirectorySelector>;

const DAY = 86_400_000;
const MOCK_NOW = Date.UTC(2026, 6, 22);

function folder(name: string, daysAgo: number): DirectoryEntry {
  return { name, kind: 'directory', addedAtMs: MOCK_NOW - daysAgo * DAY };
}

function repo(name: string, daysAgo: number): DirectoryEntry {
  return { name, kind: 'repository', addedAtMs: MOCK_NOW - daysAgo * DAY };
}

function file(name: string, sizeBytes: number, daysAgo: number): DirectoryEntry {
  return { name, kind: 'file', sizeBytes, addedAtMs: MOCK_NOW - daysAgo * DAY };
}

function symlink(name: string, daysAgo: number): DirectoryEntry {
  return { name, kind: 'symlink', addedAtMs: MOCK_NOW - daysAgo * DAY };
}

const mockFs: Record<string, DirectoryEntry[]> = {
  '/home/user': [
    folder('repos', 64),
    repo('emdash', 14),
    folder('Downloads', 3),
    folder('empty-folder', 1),
    file('.zshrc', 3_421, 90),
  ],
  '/home/user/repos': [repo('emdash', 14), folder('plugins', 22), file('README.md', 12_420, 21)],
  '/home/user/repos/emdash': [
    folder('apps', 13),
    folder('packages', 13),
    folder('.git', 14),
    file('package.json', 5_125, 2),
    file('pnpm-lock.yaml', 643_220, 2),
  ],
  '/home/user/repos/emdash/apps': [repo('emdash-desktop', 13), file('README.md', 8_032, 12)],
  '/home/user/repos/emdash/packages': [repo('ui', 13), folder('core', 13), folder('shared', 13)],
  '/home/user/repos/plugins': [folder('providers', 20), symlink('current', 4)],
  '/home/user/emdash': [folder('src', 14), folder('.git', 14), file('README.md', 15_248, 9)],
  '/home/user/Downloads': [file('archive.zip', 4_932_812, 8), folder('screenshots', 3)],
  '/home/user/Downloads/screenshots': [
    file('settings.png', 812_400, 3),
    file('workbench.png', 1_284_330, 3),
  ],
  '/home/user/empty-folder': [],
};

const windowsFs: Record<string, DirectoryEntry[]> = {
  'C:': [folder('Users', 200)],
  'C:\\Users': [folder('david', 180)],
  'C:\\Users\\david': [folder('Documents', 120), repo('emdash', 6), file('notes.txt', 3_104, 11)],
  'C:\\Users\\david\\Documents': [folder('repos', 60), folder('designs', 15)],
};

export const Interactive: Story = {
  render: () => <MockDirectorySelector initialPath="/home/user" fs={mockFs} />,
};

export const Loading: Story = {
  args: {
    path: '/home/user',
    listing: { status: 'loading' },
    selectedPath: null,
    canGoBack: false,
    canGoForward: false,
    onBack: noop,
    onForward: noop,
    onNavigate: noop,
    onSelect: noop,
  },
  render: (args) => (
    <div style={{ width: '34rem' }}>
      <DirectorySelector {...args} />
    </div>
  ),
};

export const Error: Story = {
  args: {
    path: '/home/user/private',
    listing: { status: 'error', message: 'Permission denied' },
    selectedPath: null,
    canGoBack: true,
    canGoForward: false,
    onBack: noop,
    onForward: noop,
    onNavigate: noop,
    onSelect: noop,
  },
  render: (args) => (
    <div style={{ width: '34rem' }}>
      <DirectorySelector {...args} />
    </div>
  ),
};

export const EmptyFolder: Story = {
  args: {
    path: '/home/user/empty-folder',
    listing: { status: 'ready', entries: [] },
    selectedPath: null,
    canGoBack: true,
    canGoForward: false,
    onBack: noop,
    onForward: noop,
    onNavigate: noop,
    onSelect: noop,
  },
  render: (args) => (
    <div style={{ width: '34rem' }}>
      <DirectorySelector {...args} />
    </div>
  ),
};

export const WithSelection: Story = {
  args: {
    path: '/home/user',
    listing: { status: 'ready', entries: mockFs['/home/user']! },
    selectedPath: '/home/user/emdash',
    canGoBack: false,
    canGoForward: false,
    onBack: noop,
    onForward: noop,
    onNavigate: noop,
    onSelect: noop,
    onCreateFolder: noop,
    onCancel: noop,
    onConfirm: noop,
  },
  render: (args) => (
    <div style={{ width: '34rem' }}>
      <DirectorySelector {...args} />
    </div>
  ),
};

export const WindowsSeparator: Story = {
  render: () => (
    <MockDirectorySelector initialPath="C:\\Users\\david" fs={windowsFs} separator={'\\'} />
  ),
};

function MockDirectorySelector({
  initialPath,
  fs,
  separator = '/',
}: {
  initialPath: string;
  fs: Record<string, DirectoryEntry[]>;
  separator?: '/' | '\\';
}) {
  const history = useDirectoryHistory(initialPath);
  const [fsState, setFsState] = React.useState(() => cloneFs(fs));
  const [selectedPath, setSelectedPath] = React.useState<string | null>(null);
  const [listing, setListing] = React.useState<DirectoryListing>({ status: 'loading' });
  const [confirmedPath, setConfirmedPath] = React.useState<string | null>(null);

  React.useEffect(() => {
    setSelectedPath(null);
    setListing({ status: 'loading' });
    const timer = window.setTimeout(() => {
      const entries = fsState[history.path];
      setListing(
        entries
          ? { status: 'ready', entries }
          : { status: 'error', message: `Folder not found: ${history.path}` }
      );
    }, 250);
    return () => window.clearTimeout(timer);
  }, [fsState, history.path]);

  React.useEffect(() => {
    setFsState(cloneFs(fs));
  }, [fs]);

  function createFolder(parentPath: string, name: string) {
    setFsState((current) => {
      const currentEntries = current[parentPath] ?? [];
      if (currentEntries.some((entry) => entry.name === name)) return current;
      const newPath = joinStoryPath(parentPath, name, separator);
      return {
        ...current,
        [parentPath]: [
          { name, kind: 'directory', addedAtMs: Date.now() } satisfies DirectoryEntry,
          ...currentEntries,
        ],
        [newPath]: [],
      };
    });
  }

  return (
    <div style={{ display: 'grid', width: '34rem', gap: '0.5rem' }}>
      <DirectorySelector
        path={history.path}
        listing={listing}
        selectedPath={selectedPath}
        canGoBack={history.canGoBack}
        canGoForward={history.canGoForward}
        onBack={history.back}
        onForward={history.forward}
        onNavigate={history.navigate}
        onSelect={setSelectedPath}
        onCreateFolder={createFolder}
        onCancel={() => setSelectedPath(null)}
        onConfirm={setConfirmedPath}
        separator={separator}
      />
      {confirmedPath && (
        <p style={{ margin: 0, fontSize: '0.75rem', opacity: 0.7 }}>Confirmed: {confirmedPath}</p>
      )}
    </div>
  );
}

function cloneFs(fs: Record<string, DirectoryEntry[]>): Record<string, DirectoryEntry[]> {
  return Object.fromEntries(Object.entries(fs).map(([path, entries]) => [path, [...entries]]));
}

function joinStoryPath(parent: string, name: string, separator: '/' | '\\'): string {
  if (!parent || parent === separator) return `${separator}${name}`;
  return `${parent.replace(new RegExp(`${escapeRegExp(separator)}+$`), '')}${separator}${name}`;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function noop() {}
