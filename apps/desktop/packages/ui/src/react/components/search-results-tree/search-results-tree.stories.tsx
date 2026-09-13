import type { Meta, StoryObj } from '@storybook/react-vite';
import * as React from 'react';
import {
  SearchResultsTree,
  type SearchResultFile,
  type SearchResultMatch,
} from './search-results-tree';

const meta: Meta<typeof SearchResultsTree> = {
  title: 'Components/SearchResultsTree',
  component: SearchResultsTree,
  parameters: { layout: 'padded' },
};
export default meta;

type Story = StoryObj<typeof SearchResultsTree>;

export const Default: Story = {
  render: () => (
    <StoryFrame note="Click file rows to collapse matches. Click a match to preview; double-click to open permanently.">
      <SearchResultsDemo files={baseResults} />
    </StoryFrame>
  ),
};

export const LargeResultSet: Story = {
  render: () => (
    <StoryFrame height="34rem" note="Virtualized result set with many files and matches.">
      <SearchResultsDemo files={largeResults()} />
    </StoryFrame>
  ),
};

export const HighlightEdgeCases: Story = {
  render: () => (
    <StoryFrame note="Ranges are one-based, clamped, and merged when adjacent or overlapping.">
      <SearchResultsDemo files={highlightEdgeResults} />
    </StoryFrame>
  ),
};

function SearchResultsDemo({ files }: { files: readonly SearchResultFile[] }) {
  const [lastOpen, setLastOpen] = React.useState<string>('No match opened yet');
  return (
    <div style={{ display: 'flex', height: '100%', minHeight: 0, flexDirection: 'column' }}>
      <SearchResultsTree
        files={files}
        className="min-h-0 flex-1"
        onOpenMatch={(file, match, { preview }) => {
          setLastOpen(`${preview ? 'Preview' : 'Open'} ${file.path}:${match.lineNumber}`);
        }}
      />
      <div
        style={{
          flexShrink: 0,
          borderTop: '1px solid var(--em-border)',
          padding: '0.5rem',
          fontSize: 12,
          color: 'var(--em-foreground-muted)',
        }}
      >
        {lastOpen}
      </div>
    </div>
  );
}

function StoryFrame({
  height = '28rem',
  note,
  children,
}: {
  height?: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: 'grid', width: '42rem', gap: 8 }}>
      {note ? (
        <p style={{ margin: 0, fontSize: 12, color: 'var(--em-foreground-muted)' }}>{note}</p>
      ) : null}
      <div
        style={{
          height,
          minHeight: 0,
          overflow: 'hidden',
          border: '1px solid var(--em-border)',
          borderRadius: 'var(--em-radius-lg)',
        }}
      >
        {children}
      </div>
    </div>
  );
}

const baseResults: SearchResultFile[] = [
  fileResult('src/core/features/editor/browser/task-editor/file-content-search.tsx', [
    match(87, 'lease = await jobs.start({ workspaceId, query: debouncedQuery });', [
      [39, 50],
      [59, 64],
    ]),
    match(170, 'const openMatch = (path: string, match: ContentSearchLineMatch) => {', [
      [7, 16],
      [38, 43],
    ]),
  ]),
  fileResult('packages/ui/src/react/components/file-tree/file-tree.tsx', [
    match(256, 'React.useImperativeHandle(ref, () => ({ startDraft, collapseAll, expandAll }));', [
      [7, 26],
      [42, 52],
    ]),
    match(445, 'isExpanded ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />', [
      [1, 11],
      [15, 30],
      [50, 67],
    ]),
    match(746, 'return <FileIcon className={styles.fileIcon} size={12} />;', [[9, 17]]),
  ]),
  fileResult('packages/core/src/runtimes/file-search/node/exclusions.ts', [
    match(
      72,
      'return this.segments.flatMap((segment) => [`!**/${segment}`, `!**/${segment}/**`]);',
      [
        [13, 21],
        [49, 56],
        [66, 73],
      ]
    ),
  ]),
];

const highlightEdgeResults: SearchResultFile[] = [
  fileResult('src/highlight-overlap.ts', [
    match(12, 'const searchable = "overlapping searchable ranges";', [
      [7, 17],
      [13, 29],
      [29, 39],
    ]),
    match(19, 'short', [
      [0, 2],
      [4, 99],
    ]),
    match(24, 'no valid highlight ranges on this row', []),
  ]),
  fileResult('src/long-preview.ts', [
    match(
      42,
      'const preview = veryLongLineWithMultipleSegmentsThatShouldStayOnASingleTruncatedRow();',
      [
        [17, 29],
        [53, 69],
      ]
    ),
  ]),
];

function largeResults(): SearchResultFile[] {
  return Array.from({ length: 120 }, (_, fileIndex) =>
    fileResult(
      `src/generated/module-${fileIndex + 1}/search-result-${fileIndex + 1}.ts`,
      Array.from({ length: 8 }, (_, matchIndex) =>
        match(
          matchIndex * 7 + 3,
          `export const searchResult${fileIndex}_${matchIndex} = "query match ${matchIndex}";`,
          [
            [14, 26],
            [54, 59],
          ]
        )
      )
    )
  );
}

function fileResult(path: string, matches: SearchResultMatch[]): SearchResultFile {
  const slash = path.lastIndexOf('/');
  return {
    path,
    name: slash >= 0 ? path.slice(slash + 1) : path,
    directory: slash >= 0 ? path.slice(0, slash) : '',
    occurrenceCount: matches.reduce((total, match) => total + match.highlightRanges.length, 0),
    matches,
  };
}

function match(
  lineNumber: number,
  previewText: string,
  ranges: Array<[number, number]>
): SearchResultMatch {
  return {
    lineNumber,
    previewText,
    highlightRanges: ranges.map(([startColumn, endColumn]) => ({ startColumn, endColumn })),
  };
}
