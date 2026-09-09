import { Box } from '@react/primitives/box';
import { Switch } from '@react/primitives/switch';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/Switch',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Default: Story = {
  render: () => <Switch aria-label="Enable feature" />,
};

export const Controlled: Story = {
  render: function ControlledSwitch() {
    const [checked, setChecked] = useState(false);
    return (
      <Box display="flex" alignItems="center" gap="2">
        <Switch checked={checked} onCheckedChange={setChecked} aria-label="Telemetry" />
        <span style={{ fontSize: 'var(--em-text-sm)' }}>{checked ? 'On' : 'Off'}</span>
      </Box>
    );
  },
};

/** Base (32×18 px) vs SM (24×14 px) sizes. */
export const Sizes: Story = {
  render: () => (
    <Box display="flex" alignItems="center" gap="3">
      <Switch defaultChecked size="base" aria-label="Base size" />
      <Switch defaultChecked size="sm" aria-label="Small size" />
      <Switch size="sm" aria-label="Small size off" />
    </Box>
  ),
};

export const Disabled: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w72}>
      <Switch disabled aria-label="Disabled off" />
      <Switch disabled defaultChecked aria-label="Disabled on" />
    </Box>
  ),
};

export const InFormRow: Story = {
  render: () => (
    <Box
      display="flex"
      alignItems="center"
      justifyContent="space-between"
      gap="4"
      className={s.w72}
    >
      <Box display="flex" flexDirection="column" gap="1">
        <span style={{ fontSize: 'var(--em-text-sm)', fontWeight: 400 }}>Send telemetry</span>
        <span style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)' }}>
          Anonymous usage data helps us improve.
        </span>
      </Box>
      <Switch defaultChecked aria-label="Send telemetry" />
    </Box>
  ),
};
