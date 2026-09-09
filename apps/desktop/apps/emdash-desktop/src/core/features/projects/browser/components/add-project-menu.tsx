import { DropdownMenu } from '@emdash/ui/react/primitives';
import { FilePlus2, FolderOpen } from 'lucide-react';
import type { ReactElement } from 'react';
import { useOpenProjectFolder } from '../open-project-folder';

/**
 * Codex-style project entry: adding a project is a small starting-point menu,
 * not a wizard. Both choices resolve to an ordinary local folder.
 */
export function AddProjectMenu({
  trigger,
  align = 'end',
}: {
  trigger: ReactElement;
  align?: 'start' | 'center' | 'end';
}) {
  const projectFolder = useOpenProjectFolder();

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger render={trigger} />
      <DropdownMenu.Content align={align} width="content-at-least-trigger">
        <DropdownMenu.Item
          disabled={projectFolder.busy}
          onClick={() => void projectFolder.open('scratch')}
        >
          <FilePlus2 className="size-4" />
          Start from scratch
        </DropdownMenu.Item>
        <DropdownMenu.Item
          disabled={projectFolder.busy}
          onClick={() => void projectFolder.open('existing')}
        >
          <FolderOpen className="size-4" />
          Use an existing folder
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
