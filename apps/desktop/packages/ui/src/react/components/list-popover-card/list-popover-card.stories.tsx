import { Button } from '@react/primitives/button';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { AlertCircle, Trash2, X } from 'lucide-react';
import { ListPopoverCard } from './list-popover-card';

const meta: Meta<typeof ListPopoverCard> = {
  title: 'Components/ListPopoverCard',
  component: ListPopoverCard,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <div
        style={{
          position: 'relative',
          height: '16rem',
          overflow: 'hidden',
          background: 'var(--em-background)',
        }}
      >
        <div style={{ padding: '1rem', color: 'var(--em-foreground-passive)' }}>
          List content behind the card…
        </div>
        <Story />
      </div>
    ),
  ],
};

export default meta;
type Story = StoryObj<typeof ListPopoverCard>;

export const SelectionBar: Story = {
  render: () => (
    <ListPopoverCard style={{ justifyContent: 'space-between' }}>
      <span style={{ whiteSpace: 'nowrap', color: 'var(--em-foreground-muted)' }}>3 selected</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <Button variant="destructive" size="sm">
          <Trash2 size={14} />
          Delete
        </Button>
        <Button variant="ghost" size="xs" icon aria-label="Clear selection">
          <X size={14} />
        </Button>
      </div>
    </ListPopoverCard>
  ),
};

export const Destructive: Story = {
  render: () => (
    <ListPopoverCard status="destructive">
      <AlertCircle size={14} style={{ flexShrink: 0 }} />
      <span style={{ fontWeight: 500, flexShrink: 0 }}>Sync failed</span>
      <span
        style={{
          minWidth: 0,
          flexGrow: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        GitHub authentication expired — reconnect to resume syncing pull requests.
      </span>
      <Button variant="secondary" size="xs">
        Reconnect
      </Button>
    </ListPopoverCard>
  ),
};

export const Info: Story = {
  render: () => (
    <ListPopoverCard status="info">
      <span style={{ minWidth: 0, flexGrow: 1 }}>Syncing PRs: 12 / 250</span>
      <Button variant="ghost" size="sm">
        Cancel
      </Button>
    </ListPopoverCard>
  ),
};
