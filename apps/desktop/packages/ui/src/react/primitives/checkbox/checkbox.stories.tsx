import { Box } from '@react/primitives/box';
import { Checkbox } from '@react/primitives/checkbox';
import { Field } from '@react/primitives/field';
import { Label } from '@react/primitives/label';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/Checkbox',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Default: Story = {
  render: () => <Checkbox aria-label="Accept" />,
};

export const Controlled: Story = {
  render: function ControlledCheckbox() {
    const [checked, setChecked] = useState(true);
    return (
      <Box display="flex" alignItems="center" gap="2">
        <Checkbox checked={checked} onCheckedChange={setChecked} aria-label="Notifications" />
        <span style={{ fontSize: 'var(--em-text-sm)' }}>{checked ? 'Checked' : 'Unchecked'}</span>
      </Box>
    );
  },
};

export const States: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w72}>
      <Box display="flex" alignItems="center" gap="2">
        <Checkbox aria-label="Unchecked" />
        <span style={{ fontSize: 'var(--em-text-sm)' }}>Unchecked</span>
      </Box>
      <Box display="flex" alignItems="center" gap="2">
        <Checkbox defaultChecked aria-label="Checked" />
        <span style={{ fontSize: 'var(--em-text-sm)' }}>Checked</span>
      </Box>
      <Box display="flex" alignItems="center" gap="2">
        <Checkbox disabled aria-label="Disabled" />
        <span style={{ fontSize: 'var(--em-text-sm)' }}>Disabled</span>
      </Box>
      <Box display="flex" alignItems="center" gap="2">
        <Checkbox disabled defaultChecked aria-label="Disabled checked" />
        <span style={{ fontSize: 'var(--em-text-sm)' }}>Disabled checked</span>
      </Box>
    </Box>
  ),
};

export const WithLabel: Story = {
  render: () => (
    <Label>
      <Checkbox defaultChecked />
      Remember this choice
    </Label>
  ),
};

export const InsideDisabledField: Story = {
  render: () => (
    <Field.Root disabled className={s.w72}>
      <Box display="flex" alignItems="center" gap="2">
        <Checkbox defaultChecked />
        <Field.Label>Sync automatically</Field.Label>
      </Box>
      <Field.Description>The whole field is disabled; the control dims.</Field.Description>
    </Field.Root>
  ),
};
