import type { Meta, StoryObj } from '@storybook/react-vite';
import { AlertCircleIcon } from 'lucide-react';
import * as React from 'react';
import { StatusIcon } from './status-icon';

const meta: Meta<typeof StatusIcon> = {
  title: 'Components/StatusIcon',
  component: StatusIcon,
  parameters: { layout: 'centered' },
};
export default meta;
type Story = StoryObj<typeof StatusIcon>;

export const Success: Story = { args: { severity: 'success' } };
export const Error: Story = { args: { severity: 'error' } };
export const Warning: Story = { args: { severity: 'warning' } };
export const Info: Story = { args: { severity: 'info' } };
export const Neutral: Story = { args: { severity: 'neutral' } };

export const Small: Story = { args: { severity: 'success', size: 'sm' } };
export const Medium: Story = { args: { severity: 'info', size: 'md' } };
export const Large: Story = { args: { severity: 'error', size: 'lg' } };

export const CustomIcon: Story = {
  args: {
    severity: 'warning',
    icon: <AlertCircleIcon style={{ width: '0.875rem', height: '0.875rem' }} />,
  },
};

export const AllSeverities: Story = {
  render: () => (
    <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
      <StatusIcon severity="success" />
      <StatusIcon severity="error" />
      <StatusIcon severity="warning" />
      <StatusIcon severity="info" />
      <StatusIcon severity="neutral" />
    </div>
  ),
};

export const AllSizes: Story = {
  render: () => (
    <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
      <StatusIcon severity="success" size="sm" />
      <StatusIcon severity="success" size="md" />
      <StatusIcon severity="success" size="lg" />
    </div>
  ),
};
