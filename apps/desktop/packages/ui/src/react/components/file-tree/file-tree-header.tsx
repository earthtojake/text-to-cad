import { CopyMinusIcon, FilePlusIcon, FolderPlusIcon } from 'lucide-react';
import { Button } from '../../primitives/button';
import * as styles from './file-tree.css';

export type FileTreeDraftKind = 'file' | 'directory';

export interface FileTreeHeaderContext {
  targetPath: string;
  startDraft(kind: FileTreeDraftKind): void;
  collapseAll(): void;
  expandAll(): void;
}

export function FileTreeHeader({ targetPath, startDraft, collapseAll }: FileTreeHeaderContext) {
  const targetLabel = targetPath ? `New items in ${targetPath}` : 'New items in root';

  return (
    <header className={styles.header}>
      <div className={styles.headerTarget} title={targetLabel}>
        {targetLabel}
      </div>
      <div className={styles.headerActions}>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          icon
          aria-label="New file"
          onClick={() => startDraft('file')}
        >
          <FilePlusIcon aria-hidden size={14} />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          icon
          aria-label="New folder"
          onClick={() => startDraft('directory')}
        >
          <FolderPlusIcon aria-hidden size={14} />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          icon
          aria-label="Collapse all"
          onClick={collapseAll}
        >
          <CopyMinusIcon aria-hidden size={14} />
        </Button>
      </div>
    </header>
  );
}
