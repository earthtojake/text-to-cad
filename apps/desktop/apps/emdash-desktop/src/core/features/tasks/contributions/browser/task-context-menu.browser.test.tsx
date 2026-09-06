import '@emdash/ui/style.css';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { TaskDropdownMenu } from './task-context-menu';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('TaskDropdownMenu', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('exposes the same chat actions visibly and does not open the row behind the menu', async () => {
    const archive = vi.fn();
    const rowClick = vi.fn();
    await act(async () =>
      root.render(
        <div onClick={rowClick}>
          <TaskDropdownMenu
            isPinned={false}
            canPin
            isArchived={false}
            onPin={vi.fn()}
            onUnpin={vi.fn()}
            onRename={vi.fn()}
            onArchive={archive}
            onDelete={vi.fn()}
            trigger={
              <button type="button" onClick={(event) => event.stopPropagation()}>
                More actions for Wheel review
              </button>
            }
          />
        </div>
      )
    );

    await act(async () => findButton(host, 'More actions for Wheel review').click());

    const labels = Array.from(document.querySelectorAll<HTMLElement>('[role="menuitem"]')).map(
      (item) => item.textContent?.trim()
    );
    expect(labels).toEqual(['Pin chat', 'Rename', 'Archive', 'Delete']);

    const archiveItem = Array.from(
      document.querySelectorAll<HTMLElement>('[role="menuitem"]')
    ).find((item) => item.textContent?.trim() === 'Archive');
    await act(async () => archiveItem?.click());

    expect(archive).toHaveBeenCalledOnce();
    expect(rowClick).not.toHaveBeenCalled();
  });
});

function findButton(host: HTMLElement, accessibleName: string): HTMLButtonElement {
  const button = Array.from(host.querySelectorAll('button')).find(
    (candidate) => candidate.textContent?.trim() === accessibleName
  );
  if (!button) throw new Error(`Could not find ${accessibleName} button`);
  return button;
}
