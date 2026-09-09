import { Box } from '@react/primitives/box';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { Heading } from './Heading';

const meta: Meta<typeof Heading> = {
  title: 'Primitives/Heading',
  component: Heading,
  parameters: { layout: 'centered' },
  argTypes: {
    level: { control: 'select', options: [1, 2, 3, 4] },
    tone: { control: 'select', options: ['default', 'muted', 'passive', 'inherit'] },
  },
};

export default meta;
type Story = StoryObj<typeof Heading>;

export const Default: Story = {
  args: {
    level: 1,
    tone: 'default',
    children: 'Build and run agents in parallel',
  },
};

export const Levels: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3">
      <Heading level={1}>Page heading</Heading>
      <Heading level={2}>Feature heading</Heading>
      <Heading level={3}>Card heading</Heading>
      <Heading level={4}>Section heading</Heading>
    </Box>
  ),
};
