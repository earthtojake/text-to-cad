import { Box } from '@react/primitives/box';
import { Textarea } from '@react/primitives/textarea';
import type { Meta, StoryObj } from '@storybook/react-vite';
import * as s from '@react/story-layout.css';

const meta: Meta<typeof Textarea> = {
  title: 'Primitives/Textarea',
  component: Textarea,
  parameters: { layout: 'centered' },
  argTypes: {
    size: { control: 'select', options: ['base', 'sm'] },
  },
};

export default meta;
type Story = StoryObj<typeof Textarea>;

export const Default: Story = {
  render: () => (
    <Box className={s.w64}>
      <Textarea placeholder="Enter text…" />
    </Box>
  ),
};

export const Sizes: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w64}>
      <Textarea size="base" placeholder="Base size textarea" />
      <Textarea size="sm" placeholder="Small size textarea" />
    </Box>
  ),
};

export const WithValue: Story = {
  render: () => (
    <Box className={s.w64}>
      <Textarea defaultValue="Some longer text that wraps over multiple lines in the textarea." />
    </Box>
  ),
};

export const Disabled: Story = {
  render: () => (
    <Box className={s.w64}>
      <Textarea placeholder="Disabled" disabled />
    </Box>
  ),
};

export const Invalid: Story = {
  render: () => (
    <Box className={s.w64}>
      <Textarea placeholder="Invalid" aria-invalid="true" />
    </Box>
  ),
};
