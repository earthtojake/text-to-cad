import { Box } from '@react/primitives/box';
import { Checkbox } from '@react/primitives/checkbox';
import { Input } from '@react/primitives/input';
import { Label, MicroLabel } from '@react/primitives/label';
import type { Meta, StoryObj } from '@storybook/react-vite';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/Label',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Default: Story = {
  render: () => <Label htmlFor="name-input">Workspace name</Label>,
};

export const WithInput: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="2" className={s.w72}>
      <Label htmlFor="branch-input">Branch name</Label>
      <Input id="branch-input" placeholder="feature/my-branch" />
    </Box>
  ),
};

export const WrappingControl: Story = {
  render: () => (
    <Label>
      <Checkbox defaultChecked />
      Enable notifications
    </Label>
  ),
};

export const Micro: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="2" className={s.w72}>
      <MicroLabel>Pinned tasks</MicroLabel>
      <span style={{ fontSize: 'var(--em-text-sm)' }}>Task list content…</span>
    </Box>
  ),
};
