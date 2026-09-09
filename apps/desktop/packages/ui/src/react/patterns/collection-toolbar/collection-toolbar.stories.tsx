import type { Meta, StoryObj } from '@storybook/react-vite';
import { PlusIcon, RefreshCwIcon, WifiOffIcon } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../primitives/button';
import { CollectionToolbar } from './collection-toolbar';

const meta = {
  title: 'Patterns/CollectionToolbar',
  component: CollectionToolbar,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof CollectionToolbar>;

export default meta;
type Story = StoryObj<typeof meta>;

const storyWidth = { width: 'min(52rem, calc(100vw - 4rem))' };

export const WithActions: Story = {
  args: {
    searchValue: '',
    onSearchValueChange: () => {},
    searchPlaceholder: 'Search skills…',
  },
  render: function WithActionsStory() {
    const [searchValue, setSearchValue] = useState('');

    return (
      <CollectionToolbar
        style={storyWidth}
        searchValue={searchValue}
        onSearchValueChange={setSearchValue}
        searchPlaceholder="Search skills…"
        actions={
          <>
            <Button variant="secondary" icon aria-label="Refresh skills">
              <RefreshCwIcon />
            </Button>
            <Button variant="primary">
              <PlusIcon />
              New Skill
            </Button>
          </>
        }
      />
    );
  },
};

export const WithMetadata: Story = {
  args: {
    searchValue: '',
    onSearchValueChange: () => {},
    searchPlaceholder: 'Search conversations, tasks, workspaces…',
  },
  render: function WithMetadataStory() {
    const [searchValue, setSearchValue] = useState('');

    return (
      <CollectionToolbar
        style={storyWidth}
        searchValue={searchValue}
        onSearchValueChange={setSearchValue}
        searchPlaceholder="Search conversations, tasks, workspaces…"
        metadata={
          <>
            <span>9 conversations</span>
            <span>
              <WifiOffIcon aria-hidden size={12} />
              Offline
            </span>
          </>
        }
      />
    );
  },
};

export const SearchOnly: Story = {
  args: {
    searchValue: '',
    onSearchValueChange: () => {},
    searchPlaceholder: 'Search agents…',
  },
  render: function SearchOnlyStory() {
    const [searchValue, setSearchValue] = useState('');

    return (
      <CollectionToolbar
        style={storyWidth}
        searchValue={searchValue}
        onSearchValueChange={setSearchValue}
        searchPlaceholder="Search agents…"
      />
    );
  },
};
