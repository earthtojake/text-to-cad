import { cx } from '@styles/utilities/cx';
import { ChevronDownIcon, ChevronRightIcon, FileIcon } from 'lucide-react';
import * as React from 'react';
import { resolveFileIconClass } from '../../lib/file-icons';
import { TreeView, type TreeNode, type TreeRow } from '../../patterns/tree-view';
import * as rowStyles from '../tree-rows';
import { highlightSegments, type SearchResultRange } from './highlight';
import * as styles from './search-results-tree.css';

const ROW_HEIGHT = 28;
const OVERSCAN = 12;

export type { HighlightSegment, SearchResultRange } from './highlight';

export interface SearchResultMatch {
  lineNumber: number;
  previewText: string;
  highlightRanges: readonly SearchResultRange[];
}

export interface SearchResultFile {
  path: string;
  name: string;
  directory: string;
  occurrenceCount: number;
  matches: readonly SearchResultMatch[];
}

export interface SearchResultsTreeProps {
  files: readonly SearchResultFile[];
  onOpenMatch(
    file: SearchResultFile,
    match: SearchResultMatch,
    options: { preview: boolean }
  ): void;
  renderFileIcon?: (file: SearchResultFile) => React.ReactNode;
  className?: string;
  ariaLabel?: string;
}

type SearchRowData =
  | { kind: 'file'; file: SearchResultFile }
  | { kind: 'match'; file: SearchResultFile; match: SearchResultMatch };

export function SearchResultsTree({
  files,
  onOpenMatch,
  renderFileIcon,
  className,
  ariaLabel = 'Search results',
}: SearchResultsTreeProps) {
  const rootRef = React.useRef<HTMLDivElement>(null);
  const [collapsedPaths, setCollapsedPaths] = React.useState<ReadonlySet<string>>(new Set());

  const nodes = React.useMemo(() => buildSearchTreeNodes(files), [files]);
  const expandedIds = React.useMemo(() => {
    const expanded = new Set<string>();
    for (const file of files) {
      if (!collapsedPaths.has(file.path)) expanded.add(file.path);
    }
    return expanded;
  }, [collapsedPaths, files]);

  const toggleFile = React.useCallback((path: string) => {
    setCollapsedPaths((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const focusAdjacentResult = React.useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>, offset: -1 | 1) => {
      const buttons = rootRef.current?.querySelectorAll<HTMLButtonElement>('[data-search-result]');
      if (!buttons?.length) return;
      const index = [...buttons].indexOf(event.currentTarget);
      const next = buttons[index + offset];
      if (!next) return;
      event.preventDefault();
      next.focus();
    },
    []
  );

  return (
    <div ref={rootRef} className={cx(styles.root, className)} role="tree" aria-label={ariaLabel}>
      <TreeView
        nodes={nodes}
        expandedIds={expandedIds}
        estimateSize={ROW_HEIGHT}
        overscan={OVERSCAN}
        className={styles.viewport}
        renderRow={(row) =>
          renderRow({
            row,
            collapsedPaths,
            focusAdjacentResult,
            onOpenMatch,
            renderFileIcon,
            toggleFile,
          })
        }
      />
    </div>
  );
}

function renderRow({
  row,
  collapsedPaths,
  focusAdjacentResult,
  onOpenMatch,
  renderFileIcon,
  toggleFile,
}: {
  row: TreeRow<SearchRowData>;
  collapsedPaths: ReadonlySet<string>;
  focusAdjacentResult(event: React.KeyboardEvent<HTMLButtonElement>, offset: -1 | 1): void;
  onOpenMatch(
    file: SearchResultFile,
    match: SearchResultMatch,
    options: { preview: boolean }
  ): void;
  renderFileIcon?: (file: SearchResultFile) => React.ReactNode;
  toggleFile(path: string): void;
}) {
  if (row.node.data.kind === 'file') {
    const { file } = row.node.data;
    const collapsed = collapsedPaths.has(file.path);
    return (
      <button
        type="button"
        data-search-result
        className={rowStyles.row}
        style={rowIndentStyle(row.depth)}
        onClick={() => toggleFile(file.path)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') focusAdjacentResult(event, 1);
          if (event.key === 'ArrowUp') focusAdjacentResult(event, -1);
        }}
        role="treeitem"
        aria-expanded={!collapsed}
        title={file.path}
      >
        <span className={rowStyles.chevron} aria-hidden>
          {collapsed ? <ChevronRightIcon size={14} /> : <ChevronDownIcon size={14} />}
        </span>
        <span className={styles.fileIcon} aria-hidden>
          {renderFileIcon ? renderFileIcon(file) : defaultFileIcon(file)}
        </span>
        <span className={rowStyles.label}>
          <span className={cx(rowStyles.name, styles.fileName)}>{file.name}</span>
          {file.directory ? <span className={rowStyles.secondary}>{file.directory}</span> : null}
        </span>
        <span className={styles.count}>{file.occurrenceCount}</span>
      </button>
    );
  }

  const { file, match } = row.node.data;
  return (
    <button
      type="button"
      data-search-result
      className={cx(rowStyles.row, styles.matchRow)}
      style={rowIndentStyle(row.depth)}
      onClick={() => onOpenMatch(file, match, { preview: true })}
      onDoubleClick={() => onOpenMatch(file, match, { preview: false })}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown') focusAdjacentResult(event, 1);
        if (event.key === 'ArrowUp') focusAdjacentResult(event, -1);
      }}
      role="treeitem"
      title={`${file.path}:${match.lineNumber}`}
    >
      <span className={styles.lineNumber}>{match.lineNumber}</span>
      <span className={styles.preview}>
        {highlightSegments(match.previewText, match.highlightRanges).map((segment, index) =>
          segment.highlighted ? (
            <mark key={index} className={styles.highlight}>
              {segment.text}
            </mark>
          ) : (
            <span key={index}>{segment.text}</span>
          )
        )}
      </span>
    </button>
  );
}

function buildSearchTreeNodes(files: readonly SearchResultFile[]): TreeNode<SearchRowData>[] {
  return files.map((file) => ({
    id: file.path,
    data: { kind: 'file', file },
    children: file.matches.map((match) => ({
      id: matchId(file.path, match),
      data: { kind: 'match', file, match },
    })),
  }));
}

function matchId(path: string, match: SearchResultMatch): string {
  return `${path}:${match.lineNumber}`;
}

function rowIndentStyle(depth: number): React.CSSProperties {
  return {
    '--file-tree-row-indent': `${depth * 12 + 4}px`,
  } as React.CSSProperties;
}

function defaultFileIcon(file: SearchResultFile): React.ReactNode {
  const iconClass = resolveFileIconClass(file.name);
  if (iconClass) return <i className={cx(styles.devicon, iconClass)} />;
  return <FileIcon size={12} />;
}
