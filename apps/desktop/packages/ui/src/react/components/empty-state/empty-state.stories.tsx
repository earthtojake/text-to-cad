import { Button } from '@react/primitives/button';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { EmptyState } from './empty-state';

const meta: Meta<typeof EmptyState> = {
  title: 'Components/EmptyState',
  component: EmptyState,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <div style={{ height: '20rem', display: 'flex' }}>
        <Story />
      </div>
    ),
  ],
  args: {
    label: 'No tasks yet',
  },
};

export default meta;
type Story = StoryObj<typeof EmptyState>;

export const Default: Story = {};

export const WithDescription: Story = {
  args: {
    label: 'No pull requests',
    description: 'Pull requests opened from this project will show up here.',
  },
};

export const WithAction: Story = {
  args: {
    label: 'No terminals open',
    description: 'Open a terminal to run commands in this workspace.',
    action: <Button variant="primary">New terminal</Button>,
  },
};

/**
 * `bare` drops the panel background for containers that paint their own
 * surface (e.g. `CollectionView`'s card). The striped backdrop here shows
 * through to make the transparency visible.
 */
export const Bare: Story = {
  args: {
    label: 'No pull requests',
    description: 'Rendered with `bare` — the container behind shows through.',
    bare: true,
  },
  decorators: [
    (Story) => (
      <div
        style={{
          flex: 1,
          display: 'flex',
          background:
            'repeating-linear-gradient(45deg, rgba(128,128,128,0.12) 0 12px, transparent 12px 24px)',
        }}
      >
        <Story />
      </div>
    ),
  ],
};
