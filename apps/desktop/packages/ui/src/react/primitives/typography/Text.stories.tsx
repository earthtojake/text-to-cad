import { Box } from '@react/primitives/box';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { Text } from './Text';

const variants = [
  'body',
  'bodyItalic',
  'bodyLink',
  'h1',
  'h2',
  'h3',
  'section',
  'caption',
  'description',
  'inlineCode',
  'code',
  'codeLang',
  'mention',
] as const;

const meta: Meta<typeof Text> = {
  title: 'Primitives/Text',
  component: Text,
  parameters: { layout: 'centered' },
  argTypes: {
    variant: { control: 'select', options: variants },
    tone: { control: 'select', options: ['default', 'muted', 'passive', 'inherit'] },
  },
};

export default meta;
type Story = StoryObj<typeof Text>;

export const Default: Story = {
  args: {
    variant: 'body',
    tone: 'default',
    children: 'Run multiple coding agents in parallel.',
  },
};

export const AllVariants: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3">
      {variants.map((variant) => (
        <Box key={variant} display="flex" alignItems="baseline" gap="4">
          <Text variant="caption" tone="passive">
            {variant}
          </Text>
          <Text variant={variant}>The quick brown fox jumps over the lazy dog.</Text>
        </Box>
      ))}
    </Box>
  ),
};
