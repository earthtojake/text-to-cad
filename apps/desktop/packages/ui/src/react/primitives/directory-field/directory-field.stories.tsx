import type { Meta, StoryObj } from '@storybook/react-vite';
import { DirectoryField } from './index';

const meta: Meta<typeof DirectoryField> = {
  title: 'Primitives/DirectoryField',
  component: DirectoryField,
  parameters: { layout: 'centered' },
  render: (args) => (
    <div style={{ width: '24rem' }}>
      <DirectoryField {...args} />
    </div>
  ),
};

export default meta;
type Story = StoryObj<typeof DirectoryField>;

export const Placeholder: Story = {
  args: {
    placeholder: 'Select a directory',
    onClick: noop,
  },
};

export const WithPath: Story = {
  args: {
    path: '/Users/david/Documents/repos/emdash',
    onClick: noop,
  },
};

export const Disabled: Story = {
  args: {
    disabled: true,
    placeholder: 'Select a machine first',
    onClick: noop,
  },
};

export const Small: Story = {
  args: {
    size: 'sm',
    path: '~/repos/emdash',
    onClick: noop,
  },
};

function noop() {}
