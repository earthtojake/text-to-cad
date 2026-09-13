import type { Meta, StoryObj } from '@storybook/react-vite';
import * as React from 'react';
import { Icon, type IconSize } from './index';

const meta = {
  title: 'Primitives/Icon',
  component: Icon,
  args: {
    name: 'settings',
    size: 'md',
  },
} satisfies Meta<typeof Icon>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

const SIZES: IconSize[] = ['xs', 'sm', 'md', 'lg', 'xl'];

export const Sizes: Story = {
  render: () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
      {SIZES.map((size) => (
        <div
          key={size}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.375rem',
            color: 'var(--em-foreground)',
            fontSize: 'var(--em-text-xs)',
          }}
        >
          <Icon name="bot" size={size} />
          {size}
        </div>
      ))}
    </div>
  ),
};

export const NamedIcons: Story = {
  render: () => (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
        gap: '1rem',
        color: 'var(--em-foreground)',
      }}
    >
      {(['settings', 'user', 'bot', 'external-link'] as const).map((name) => (
        <div key={name} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Icon name={name} />
          <span style={{ fontSize: 'var(--em-text-xs)' }}>{name}</span>
        </div>
      ))}
    </div>
  ),
};
