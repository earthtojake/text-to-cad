import { cx } from '@styles/utilities/cx';
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  FileIcon,
  FolderPlusIcon,
  FolderGit2Icon,
  FolderIcon,
  Link2Icon,
  Loader2Icon,
} from 'lucide-react';
import * as React from 'react';
import { Breadcrumbs, type BreadcrumbItem } from '../../primitives/breadcrumbs';
import { Button } from '../../primitives/button';
import { ScrollContainer } from '../../primitives/scroll-container';
import { SearchInput } from '../../primitives/search-input';
import * as styles from './directory-selector.css';

export interface DirectoryEntry {
  name: string;
  kind: 'directory' | 'repository' | 'file' | 'symlink';
  sizeBytes?: number;
  addedAtMs?: number;
}

export type DirectoryListing =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; entries: DirectoryEntry[] };

export interface DirectorySelectorProps {
  path: string;
  navigationRoot?: string;
  listing: DirectoryListing;
  selectedPath?: string | null;
  canGoBack: boolean;
  canGoForward: boolean;
  onBack(): void;
  onForward(): void;
  onNavigate(path: string): void;
  onSelect(path: string | null): void;
  onCreateFolder?(parentPath: string, name: string): void;
  onCancel?(): void;
  onConfirm?(path: string): void;
  separator?: '/' | '\\';
  className?: string;
}

export function DirectorySelector({
  path,
  navigationRoot,
  listing,
  selectedPath,
  canGoBack,
  canGoForward,
  onBack,
  onForward,
  onNavigate,
  onSelect,
  onCreateFolder,
  onCancel,
  onConfirm,
  separator = '/',
  className,
}: DirectorySelectorProps) {
  const [query, setQuery] = React.useState('');
  const [isCreatingFolder, setIsCreatingFolder] = React.useState(false);

  React.useEffect(() => {
    setQuery('');
    setIsCreatingFolder(false);
  }, [path]);

  const folderName = basename(path, separator);
  const filteredEntries =
    listing.status === 'ready'
      ? listing.entries.filter((entry) => matchesQuery(entry.name, query))
      : [];
  const breadcrumbs = React.useMemo(
    () => pathToBreadcrumbs(path, separator, onNavigate, navigationRoot),
    [navigationRoot, onNavigate, path, separator]
  );
  const hasFooterActions = !!onCreateFolder || !!onCancel || !!onConfirm;

  return (
    <section className={cx(styles.root, className)} aria-label="Directory selector">
      <header className={styles.header}>
        <div className={styles.navigationControls}>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            icon
            disabled={!canGoBack}
            aria-label="Go back"
            onClick={onBack}
          >
            <ChevronLeftIcon aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            icon
            disabled={!canGoForward}
            aria-label="Go forward"
            onClick={onForward}
          >
            <ChevronRightIcon aria-hidden />
          </Button>
        </div>
        <div className={styles.currentFolder} title={path}>
          {folderName}
        </div>
        <div className={styles.searchSlot}>
          <SearchInput
            size="sm"
            className={styles.searchInput}
            value={query}
            placeholder="Search"
            onChange={(event) => setQuery(event.currentTarget.value)}
            onClear={() => setQuery('')}
          />
        </div>
      </header>

      <div className={styles.columnHeader} aria-hidden>
        <span />
        <span>Name</span>
        <span className={styles.rowMetaEnd}>Size</span>
        <span>Kind</span>
        <span>Date Added</span>
      </div>

      <ScrollContainer maxHeight={320} topFade={false} viewportClassName={styles.list}>
        {isCreatingFolder && (
          <DraftFolderRow
            onCommit={(name) => {
              onCreateFolder?.(path, name);
              setIsCreatingFolder(false);
            }}
            onDismiss={() => setIsCreatingFolder(false)}
          />
        )}
        {listing.status === 'loading' ? (
          <DirectoryState>
            <Loader2Icon aria-hidden className={styles.spinner} />
            Loading folder
          </DirectoryState>
        ) : listing.status === 'error' ? (
          <DirectoryState error>{listing.message}</DirectoryState>
        ) : listing.entries.length === 0 ? (
          isCreatingFolder ? null : (
            <DirectoryState>Empty folder</DirectoryState>
          )
        ) : filteredEntries.length === 0 ? (
          isCreatingFolder ? null : (
            <DirectoryState>No matches</DirectoryState>
          )
        ) : (
          filteredEntries.map((entry) => {
            const entryPath = joinPath(path, entry.name, separator);
            const selectable = isSelectableEntry(entry);
            const selected = selectable && selectedPath === entryPath;
            return (
              <DirectoryRow
                key={`${entry.kind}:${entry.name}`}
                entry={entry}
                path={entryPath}
                selected={selected}
                selectable={selectable}
                onNavigate={onNavigate}
                onSelect={onSelect}
              />
            );
          })
        )}
      </ScrollContainer>

      <footer className={styles.footer}>
        <Breadcrumbs items={breadcrumbs} label="Current directory path" />
        {hasFooterActions && (
          <div className={styles.footerActions}>
            {onCreateFolder && (
              <Button
                type="button"
                variant="secondary"
                size="xs"
                disabled={isCreatingFolder}
                onClick={() => setIsCreatingFolder(true)}
              >
                <FolderPlusIcon aria-hidden />
                New Folder
              </Button>
            )}
            <div className={styles.footerActionsRight}>
              {onCancel && (
                <Button type="button" variant="secondary" size="xs" onClick={onCancel}>
                  Cancel
                </Button>
              )}
              {onConfirm && (
                <Button
                  type="button"
                  variant="primary"
                  size="xs"
                  disabled={!selectedPath}
                  onClick={() => {
                    if (selectedPath) onConfirm(selectedPath);
                  }}
                >
                  Confirm
                </Button>
              )}
            </div>
          </div>
        )}
      </footer>
    </section>
  );
}

function DirectoryRow({
  entry,
  path,
  selected,
  selectable,
  onNavigate,
  onSelect,
}: {
  entry: DirectoryEntry;
  path: string;
  selected: boolean;
  selectable: boolean;
  onNavigate(path: string): void;
  onSelect(path: string | null): void;
}) {
  const label = entryKindLabel(entry.kind);
  return (
    <button
      type="button"
      className={styles.row}
      disabled={!selectable}
      data-selected={selected ? '' : undefined}
      data-disabled={!selectable ? '' : undefined}
      aria-disabled={!selectable}
      aria-pressed={selectable ? selected : undefined}
      title={path}
      onClick={() => {
        if (!selectable) return;
        onSelect(selected ? null : path);
      }}
      onDoubleClick={() => {
        if (selectable) onNavigate(path);
      }}
      onKeyDown={(event) => {
        if (!selectable || event.key !== 'Enter') return;
        event.preventDefault();
        onNavigate(path);
      }}
    >
      <EntryIcon entry={entry} />
      <span className={styles.rowName}>{entry.name}</span>
      <span className={cx(styles.rowMeta, styles.rowMetaEnd)}>{formatBytes(entry.sizeBytes)}</span>
      <span className={styles.rowMeta}>{label}</span>
      <span className={styles.rowMeta}>{formatDate(entry.addedAtMs)}</span>
    </button>
  );
}

function DraftFolderRow({
  onCommit,
  onDismiss,
}: {
  onCommit(name: string): void;
  onDismiss(): void;
}) {
  const [value, setValue] = React.useState('');
  const inputRef = React.useRef<HTMLInputElement>(null);
  const committedRef = React.useRef(false);

  React.useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <div className={styles.draftRow}>
      <FolderIcon className={styles.rowIcon} aria-hidden />
      <input
        ref={inputRef}
        className={styles.draftInput}
        value={value}
        placeholder="New folder name"
        aria-label="New folder name"
        spellCheck={false}
        onChange={(event) => setValue(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            const name = value.trim();
            if (!name) {
              onDismiss();
              return;
            }
            committedRef.current = true;
            onCommit(name);
          } else if (event.key === 'Escape') {
            event.preventDefault();
            onDismiss();
          }
        }}
        onBlur={() => {
          if (!committedRef.current) onDismiss();
        }}
      />
      <span className={cx(styles.rowMeta, styles.rowMetaEnd)}>—</span>
      <span className={styles.rowMeta}>Folder</span>
      <span className={styles.rowMeta}>—</span>
    </div>
  );
}

function DirectoryState({
  children,
  error = false,
}: {
  children: React.ReactNode;
  error?: boolean;
}) {
  return <div className={cx(styles.state, error && styles.stateError)}>{children}</div>;
}

function EntryIcon({ entry }: { entry: DirectoryEntry }) {
  const props = { className: styles.rowIcon, 'aria-hidden': true } as const;
  switch (entry.kind) {
    case 'directory':
      return <FolderIcon {...props} />;
    case 'repository':
      return <FolderGit2Icon {...props} />;
    case 'file':
      return <FileIcon {...props} />;
    case 'symlink':
      return <Link2Icon {...props} />;
  }
}

function isSelectableEntry(entry: DirectoryEntry): boolean {
  return entry.kind === 'directory' || entry.kind === 'repository';
}

function entryKindLabel(kind: DirectoryEntry['kind']): string {
  switch (kind) {
    case 'directory':
      return 'Folder';
    case 'repository':
      return 'Git repository';
    case 'file':
      return 'File';
    case 'symlink':
      return 'Symlink';
  }
}

function matchesQuery(name: string, query: string): boolean {
  const trimmed = query.trim();
  if (!trimmed) return true;
  return name.toLowerCase().includes(trimmed.toLowerCase());
}

const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });

function formatBytes(bytes: number | undefined): string {
  if (bytes == null) return '—';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** unitIndex;
  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatDate(ms: number | undefined): string {
  if (ms == null) return '—';
  return dateFormatter.format(new Date(ms));
}

function basename(path: string, separator: '/' | '\\'): string {
  const parts = splitPath(path, separator);
  return parts.at(-1)?.label || path || separator;
}

function joinPath(parent: string, name: string, separator: '/' | '\\'): string {
  if (!parent || parent === separator) return `${separator}${name}`;
  return `${parent.replace(new RegExp(`${escapeRegExp(separator)}+$`), '')}${separator}${name}`;
}

function pathToBreadcrumbs(
  path: string,
  separator: '/' | '\\',
  onNavigate: (path: string) => void,
  navigationRoot?: string
): BreadcrumbItem[] {
  const parts = splitPath(path, separator);
  const navigationRootIndex = navigationRoot
    ? parts.findIndex((part) => pathsEqual(part.path, navigationRoot, separator))
    : 0;
  return parts.map((part, index) => {
    const current = index === parts.length - 1;
    const withinNavigationRoot = navigationRootIndex >= 0 && index >= navigationRootIndex;
    return {
      id: part.path,
      label: part.label,
      onSelect: current || !withinNavigationRoot ? undefined : () => onNavigate(part.path),
    };
  });
}

function pathsEqual(left: string, right: string, separator: '/' | '\\'): boolean {
  const normalize = (value: string) => {
    const withoutTrailingSeparators =
      value.replace(new RegExp(`${escapeRegExp(separator)}+$`), '') || separator;
    return separator === '\\' ? withoutTrailingSeparators.toLowerCase() : withoutTrailingSeparators;
  };
  return normalize(left) === normalize(right);
}

function splitPath(path: string, separator: '/' | '\\'): Array<{ label: string; path: string }> {
  if (!path) return [];

  if (separator === '\\') {
    const [root = '', ...rest] = path.split('\\').filter(Boolean);
    const parts = root ? [{ label: root, path: root }] : [];
    for (const segment of rest) {
      const previous = parts.at(-1)?.path ?? root;
      parts.push({ label: segment, path: `${previous}\\${segment}` });
    }
    return parts;
  }

  const segments = path.split('/').filter(Boolean);
  const rootLabel = path.startsWith('/') ? '/' : segments.shift();
  if (!rootLabel) return [];

  const parts = [{ label: rootLabel, path: rootLabel === '/' ? '/' : rootLabel }];
  for (const segment of segments) {
    const previous = parts.at(-1)!.path;
    parts.push({
      label: segment,
      path: previous === '/' ? `/${segment}` : `${previous}/${segment}`,
    });
  }
  return parts;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
