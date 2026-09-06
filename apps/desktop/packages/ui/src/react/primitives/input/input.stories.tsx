import { Box } from '@react/primitives/box';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { Input } from '.';
import * as s from '@react/story-layout.css';

const meta: Meta<typeof Input> = {
  title: 'Primitives/Input',
  component: Input,
  parameters: { layout: 'centered' },
  argTypes: {
    size: { control: 'select', options: ['base', 'sm'] },
    disabled: { control: 'boolean' },
    placeholder: { control: 'text' },
  },
};

export default meta;
type Story = StoryObj<typeof Input>;

export const Default: Story = {
  render: () => (
    <Box className={s.w64}>
      <Input placeholder="Enter text…" />
    </Box>
  ),
};

export const Sizes: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w64}>
      <Input size="base" placeholder="Base (32 px)" />
      <Input size="sm" placeholder="Small (28 px)" />
    </Box>
  ),
};

export const WithValue: Story = {
  render: () => (
    <Box className={s.w64}>
      <Input defaultValue="Hello world" />
    </Box>
  ),
};

export const Disabled: Story = {
  render: () => (
    <Box className={s.w64}>
      <Input placeholder="Disabled" disabled />
    </Box>
  ),
};

export const Invalid: Story = {
  render: () => (
    <Box className={s.w64}>
      <Input placeholder="Invalid" aria-invalid="true" />
    </Box>
  ),
};

export const Types: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w64}>
      <Input type="text" placeholder="Text" />
      <Input type="email" placeholder="Email" />
      <Input type="password" placeholder="Password" />
      <Input type="number" placeholder="Number" />
      <Input type="search" placeholder="Search" />
    </Box>
  ),
};
