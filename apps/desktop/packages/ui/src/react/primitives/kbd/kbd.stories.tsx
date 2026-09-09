import { Box } from '@react/primitives/box';
import { Kbd, KbdGroup } from '@react/primitives/kbd';
import type { Meta, StoryObj } from '@storybook/react-vite';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/Kbd',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Default: Story = {
  render: () => <Kbd>⌘</Kbd>,
};

export const Shortcut: Story = {
  render: () => (
    <Box display="flex" alignItems="center" gap="2" className={s.w72}>
      <Kbd>⌘</Kbd>
      <Kbd>F</Kbd>
    </Box>
  ),
};

export const Grouped: Story = {
  render: () => (
    <Box display="flex" alignItems="center" gap="2" className={s.w72}>
      <KbdGroup>
        <Kbd>⌘</Kbd>
        <Kbd>⇧</Kbd>
        <Kbd>K</Kbd>
      </KbdGroup>
    </Box>
  ),
};
