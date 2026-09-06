import { Box } from '@react/primitives/box';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { Breadcrumbs } from '.';

const meta: Meta<typeof Breadcrumbs> = {
  title: 'Primitives/Breadcrumbs',
  component: Breadcrumbs,
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj<typeof Breadcrumbs>;

export const Default: Story = {
  args: {
    items: [
      { id: 'machines', label: 'Remote Machines', onSelect: () => undefined },
      { id: 'machine', label: 'Development server' },
    ],
  },
};

export const LongLabels: Story = {
  render: () => (
    <Box style={{ width: '20rem' }}>
      <Breadcrumbs
        items={[
          { id: 'machines', label: 'Remote Machines', onSelect: () => undefined },
          {
            id: 'machine',
            label: 'A development machine with an intentionally long display name',
          },
        ]}
      />
    </Box>
  ),
};
