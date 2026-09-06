/**
 * @vitest-environment jsdom
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { CollectionToolbar } from '.';
import { Button } from '../../primitives/button';

function ControlledToolbar() {
  const [searchValue, setSearchValue] = useState('agent');

  return (
    <CollectionToolbar
      searchValue={searchValue}
      onSearchValueChange={setSearchValue}
      searchPlaceholder="Search agents…"
      metadata={<span>2 agents</span>}
      actions={<Button variant="primary">Add agent</Button>}
    />
  );
}

describe('CollectionToolbar', () => {
  it('updates and clears the controlled search value', () => {
    render(<ControlledToolbar />);

    const search = screen.getByRole<HTMLInputElement>('searchbox', { name: 'Search agents…' });
    fireEvent.change(search, { target: { value: 'codex' } });
    expect(search.value).toBe('codex');

    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(search.value).toBe('');
  });

  it('renders metadata and actions in dedicated slots', () => {
    const { container } = render(<ControlledToolbar />);

    expect(
      container.querySelector('[data-slot="collection-toolbar-metadata"]')?.textContent
    ).toContain('2 agents');
    expect(
      container.querySelector('[data-slot="collection-toolbar-actions"]')?.textContent
    ).toContain('Add agent');
  });
});
