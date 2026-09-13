import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { ListViewSection } from '../virtual-list';

vi.mock('../virtual-list', () => ({
  VirtualList: <T,>({
    sections,
    renderSectionHeader,
  }: {
    sections?: ListViewSection<T>[];
    renderSectionHeader?: (section: ListViewSection<T>) => React.ReactNode;
  }) => (
    <div>
      {sections?.map((section) => (
        <div key={section.key}>{renderSectionHeader?.(section)}</div>
      ))}
    </div>
  ),
}));

vi.mock('../list-row', () => ({
  SectionHeader: ({ label, count }: { label: React.ReactNode; count?: number }) => (
    <div>
      {label} {count === undefined ? null : `(${count})`}
    </div>
  ),
}));

import { createListView } from './create-list-view';

describe('createListView sections', () => {
  it('renders default headers for virtualized sections', () => {
    const view = createListView({
      getItemId: (item: { id: string; status: string }) => item.id,
      source: { kind: 'sync', items: [{ id: 'conversation-1', status: 'Active' }] },
      sections: { by: (item) => item.status },
    });

    const markup = renderToStaticMarkup(
      <view.Root>
        <view.List renderItem={(item) => <span>{item.id}</span>} />
      </view.Root>
    );

    expect(markup).toContain('Active');
    expect(markup).toContain('(1)');
  });
});
