import { Box } from '@react/primitives/box';
import { Kbd } from '@react/primitives/kbd';
import { SearchInput } from '@react/primitives/search-input';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/SearchInput',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

// ── Default (uncontrolled) ─────────────────────────────────────────────────────

export const Default: Story = {
  render: () => <SearchInput placeholder="Search…" className={s.w72} />,
};

// ── Sizes ─────────────────────────────────────────────────────────────────────

export const Sizes: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w72}>
      <SearchInput size="base" placeholder="Base size" />
      <SearchInput size="sm" placeholder="Small size" />
    </Box>
  ),
};

// ── With clear button ─────────────────────────────────────────────────────────

export const WithClear: Story = {
  render: function WithClearDemo() {
    const [value, setValue] = useState('');
    return (
      <SearchInput
        className={s.w72}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onClear={() => setValue('')}
        placeholder="Filter tasks…"
      />
    );
  },
};

export const WithShortcut: Story = {
  render: function WithShortcutDemo() {
    const [value, setValue] = useState('');
    return (
      <SearchInput
        className={s.w72}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onClear={() => setValue('')}
        placeholder="Search settings"
        shortcut={
          <>
            <Kbd>⌘</Kbd>
            <Kbd>F</Kbd>
          </>
        }
      />
    );
  },
};

// ── Disabled ──────────────────────────────────────────────────────────────────

export const Disabled: Story = {
  render: () => (
    <SearchInput disabled defaultValue="Cannot edit" placeholder="Search…" className={s.w72} />
  ),
};

// ── In a filter bar ───────────────────────────────────────────────────────────

const ITEMS = [
  'main worktree',
  'feature/auth-improvements',
  'feature/dark-mode',
  'fix/memory-leak',
  'chore/update-deps',
  'docs/contributing',
];

export const FilterBar: Story = {
  render: function FilterBarDemo() {
    const [query, setQuery] = useState('');
    const filtered = ITEMS.filter((i) => i.toLowerCase().includes(query.toLowerCase()));

    return (
      <Box display="flex" flexDirection="column" gap="3" className={s.w72}>
        <SearchInput
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onClear={() => setQuery('')}
          placeholder="Filter branches…"
        />
        <Box display="flex" flexDirection="column" gap="1">
          {filtered.length === 0 ? (
            <span style={{ fontSize: 'var(--em-text-sm)', color: 'var(--em-foreground-muted)' }}>
              No results
            </span>
          ) : (
            filtered.map((item) => (
              <span key={item} style={{ fontSize: 'var(--em-text-sm)' }}>
                {item}
              </span>
            ))
          )}
        </Box>
      </Box>
    );
  },
};
