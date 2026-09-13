/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import * as React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ListViewSection } from '../list-view/virtual-list';

// Virtualization is exercised in the browser (Storybook); here we mock the
// virtual list so jsdom tests cover CollectionView's wiring, not measurement.
vi.mock('../list-view/virtual-list', () => ({
  VirtualList: React.forwardRef(function MockVirtualList<T>(
    {
      items,
      sections,
      renderItem,
      renderSectionHeader,
      emptySlot,
      isLoading,
      loadingSlot,
      errorSlot,
    }: {
      items?: T[];
      sections?: ListViewSection<T>[];
      renderItem: (item: T, index: number) => React.ReactNode;
      renderSectionHeader?: (section: ListViewSection<T>) => React.ReactNode;
      emptySlot?: React.ReactNode;
      isLoading?: boolean;
      loadingSlot?: React.ReactNode;
      errorSlot?: React.ReactNode;
    },
    _ref: React.Ref<unknown>
  ) {
    if (errorSlot !== undefined) return <div>{errorSlot}</div>;
    const flat = sections ? sections.flatMap((s) => s.items) : (items ?? []);
    if (isLoading && flat.length === 0) return <div>{loadingSlot}</div>;
    if (flat.length === 0) return <div>{emptySlot}</div>;
    if (sections) {
      return (
        <div>
          {sections.map((section) => (
            <div key={section.key}>
              {renderSectionHeader ? renderSectionHeader(section) : section.header}
              {section.items.map((item, i) => (
                <React.Fragment key={i}>{renderItem(item, i)}</React.Fragment>
              ))}
            </div>
          ))}
        </div>
      );
    }
    return (
      <div>
        {(items ?? []).map((item, i) => (
          <React.Fragment key={i}>{renderItem(item, i)}</React.Fragment>
        ))}
      </div>
    );
  }),
}));

import type { SortApi } from '../list-view';
import { createListView } from '../list-view';
import { CollectionView, CollectionViewCell, type CollectionViewColumn } from './collection-view';
import { SortSelect } from './sort-select';
import * as emptyStateStyles from '../../components/empty-state/empty-state.css';

interface Fixture {
  id: string;
  name: string;
  group: string;
}

const ITEMS: Fixture[] = [
  { id: 'a', name: 'Alpha', group: 'One' },
  { id: 'b', name: 'Beta', group: 'One' },
  { id: 'c', name: 'Gamma', group: 'Two' },
];

afterEach(cleanup);

const NAME_COLUMNS: CollectionViewColumn<Fixture>[] = [
  { id: 'name', width: 'minmax(0, 1fr)', cell: (item) => <span>{item.name}</span> },
];

describe('CollectionView shortcut mode', () => {
  it('renders column cells and fires onItemClick with the item', () => {
    const onItemClick = vi.fn();
    render(
      <CollectionView
        items={ITEMS}
        getItemKey={(item) => item.id}
        columns={NAME_COLUMNS}
        onItemClick={onItemClick}
      />
    );

    expect(screen.getByText('Alpha')).toBeTruthy();
    expect(screen.getByText('Gamma')).toBeTruthy();

    fireEvent.click(screen.getByText('Beta'));
    expect(onItemClick).toHaveBeenCalledTimes(1);
    expect(onItemClick.mock.calls[0][0]).toEqual(ITEMS[1]);
    expect(onItemClick.mock.calls[0][1]).toBe(1);
  });

  it('makes interactive rows keyboard-operable buttons', () => {
    const onItemClick = vi.fn();
    const { container } = render(
      <CollectionView
        items={ITEMS}
        getItemKey={(item) => item.id}
        columns={NAME_COLUMNS}
        onItemClick={onItemClick}
      />
    );

    const rows = container.querySelectorAll('[data-slot="list-row"]');
    expect(rows[0]?.getAttribute('role')).toBe('button');
    expect(rows[0]?.getAttribute('tabindex')).toBe('0');

    fireEvent.keyDown(rows[1]!, { key: 'Enter' });
    expect(onItemClick).toHaveBeenCalledTimes(1);
    expect(onItemClick.mock.calls[0][0]).toEqual(ITEMS[1]);
  });

  it('leaves non-interactive rows without button semantics', () => {
    const { container } = render(
      <CollectionView items={ITEMS} getItemKey={(item) => item.id} columns={NAME_COLUMNS} />
    );

    const row = container.querySelector('[data-slot="list-row"]');
    expect(row?.getAttribute('role')).toBeNull();
    expect(row?.getAttribute('tabindex')).toBeNull();
  });

  it('renders freeform rows through renderRow inside the row shell', () => {
    const { container } = render(
      <CollectionView
        items={ITEMS}
        getItemKey={(item) => item.id}
        renderRow={(item) => <em>{item.name}</em>}
      />
    );

    expect(screen.getByText('Alpha').tagName).toBe('EM');
    expect(container.querySelectorAll('[data-slot="list-row"]')).toHaveLength(3);
  });

  it('renders the empty slot when there are no items', () => {
    render(
      <CollectionView
        items={[]}
        getItemKey={(item: Fixture) => item.id}
        columns={NAME_COLUMNS}
        emptySlot={<span>Nothing here</span>}
      />
    );
    expect(screen.getByText('Nothing here')).toBeTruthy();
  });

  it('falls back to the default empty state, rendered bare on the card surface', () => {
    render(
      <CollectionView items={[]} getItemKey={(item: Fixture) => item.id} columns={NAME_COLUMNS} />
    );
    const slot = screen.getByText('No items').closest('[data-slot="empty-state"]');
    expect(slot).toBeTruthy();
    expect(slot?.className).toContain(emptyStateStyles.bare);
  });

  it('exposes the density on the root element', () => {
    const { container } = render(
      <CollectionView
        items={ITEMS}
        getItemKey={(item) => item.id}
        columns={NAME_COLUMNS}
        density="compact"
      />
    );
    expect(container.querySelector('[data-slot="list-view"]')?.getAttribute('data-density')).toBe(
      'compact'
    );
  });
});

describe('CollectionView prop guards', () => {
  // Suppress React's console noise for expected throws.
  it('rejects ambiguous data and row-style props', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<CollectionView items={ITEMS} columns={NAME_COLUMNS} />)).toThrow(
      /getItemKey/
    );
    expect(() => render(<CollectionView items={ITEMS} getItemKey={(item) => item.id} />)).toThrow(
      /columns.*renderRow|renderRow.*columns/
    );
    expect(() => render(<CollectionView columns={NAME_COLUMNS} />)).toThrow(/view.*items/);
    spy.mockRestore();
  });
});

describe('CollectionView state mode', () => {
  it('auto-derives row selected state from the view selection', () => {
    const view = createListView({
      getItemId: (item: Fixture) => item.id,
      source: { kind: 'sync', items: ITEMS },
      selection: { kind: 'multi' },
    });

    function SelectCell() {
      const { id } = view.useItem();
      const selection = view.useSelection();
      return (
        <button type="button" onClick={() => selection.toggle(id)}>
          sel-{id}
        </button>
      );
    }

    const columns: CollectionViewColumn<Fixture>[] = [
      { id: 'select', width: '2rem', cell: () => <SelectCell /> },
      ...NAME_COLUMNS,
    ];

    const { container } = render(
      <view.Root>
        <CollectionView view={view} columns={columns} />
      </view.Root>
    );

    expect(container.querySelector('[data-slot="list-row"][data-selected]')).toBeNull();
    fireEvent.click(screen.getByText('sel-a'));
    expect(container.querySelectorAll('[data-slot="list-row"][data-selected]')).toHaveLength(1);
  });

  it('applies universal selection mechanics: modifier-click toggles, shift-click ranges', () => {
    const view = createListView({
      getItemId: (item: Fixture) => item.id,
      source: { kind: 'sync', items: ITEMS },
      selection: { kind: 'multi' },
    });
    const onItemClick = vi.fn();

    const { container } = render(
      <view.Root>
        <CollectionView view={view} columns={NAME_COLUMNS} onItemClick={onItemClick} />
      </view.Root>
    );

    // Modifier-click toggles selection without navigating.
    fireEvent.click(screen.getByText('Alpha'), { metaKey: true });
    expect(onItemClick).not.toHaveBeenCalled();
    expect(container.querySelectorAll('[data-slot="list-row"][data-selected]')).toHaveLength(1);

    // Shift-click extends the range from the anchor.
    fireEvent.click(screen.getByText('Gamma'), { shiftKey: true });
    expect(container.querySelectorAll('[data-slot="list-row"][data-selected]')).toHaveLength(3);

    // A plain click stays navigation.
    fireEvent.click(screen.getByText('Beta'));
    expect(onItemClick).toHaveBeenCalledTimes(1);
    expect(onItemClick.mock.calls[0][0]).toEqual(ITEMS[1]);
  });

  it('renders default section headers and honors renderSectionHeader', () => {
    const makeView = () =>
      createListView({
        getItemId: (item: Fixture) => item.id,
        source: { kind: 'sync', items: ITEMS },
        sections: { by: (item) => item.group, order: ['One', 'Two'] },
      });

    const defaultView = makeView();
    render(
      <defaultView.Root>
        <CollectionView view={defaultView} renderRow={(item) => <span>{item.name}</span>} />
      </defaultView.Root>
    );
    expect(screen.getByText('One')).toBeTruthy();
    expect(screen.getByText('(2)')).toBeTruthy();

    const overrideView = makeView();
    render(
      <overrideView.Root>
        <CollectionView
          view={overrideView}
          renderRow={(item) => <span>{item.name}</span>}
          renderSectionHeader={(key, count) => <b>{`${key}:${count}`}</b>}
        />
      </overrideView.Root>
    );
    expect(screen.getByText('One:2')).toBeTruthy();
    expect(screen.getByText('Two:1')).toBeTruthy();
  });

  it('defaults the error slot to a bare EmptyState with the error message', async () => {
    const view = createListView({
      getItemId: (item: Fixture) => item.id,
      source: { kind: 'async', load: () => Promise.reject(new Error('boom')) },
    });

    render(
      <view.Root>
        <CollectionView view={view} columns={NAME_COLUMNS} />
      </view.Root>
    );

    const label = await screen.findByText('Something went wrong');
    expect(screen.getByText('boom')).toBeTruthy();
    const slot = label.closest('[data-slot="empty-state"]');
    expect(slot?.className).toContain(emptyStateStyles.bare);
  });

  it('renders toolbar and footer slots', () => {
    render(
      <CollectionView
        items={ITEMS}
        getItemKey={(item) => item.id}
        columns={NAME_COLUMNS}
        toolbar={<span>the toolbar</span>}
        footer={<span>the footer</span>}
      />
    );
    expect(screen.getByText('the toolbar')).toBeTruthy();
    expect(screen.getByText('the footer')).toBeTruthy();
  });
});

describe('CollectionViewCell', () => {
  it('renders primary and secondary lines', () => {
    render(<CollectionViewCell primary="Main" secondary="Detail" />);
    expect(screen.getByText('Main')).toBeTruthy();
    expect(screen.getByText('Detail')).toBeTruthy();
  });
});

describe('SortSelect', () => {
  it('shows the current key label and lists all keys', () => {
    const sort: SortApi<'name' | 'date'> = {
      key: 'name',
      dir: 'asc',
      setKey: vi.fn(),
      toggleDir: vi.fn(),
      keys: { name: { label: 'Name' }, date: { label: 'Date' } },
    };
    render(<SortSelect sort={sort} />);

    const trigger = screen.getByRole('combobox', { name: 'Sort' });
    expect(trigger.textContent).toContain('Name');
  });
});
