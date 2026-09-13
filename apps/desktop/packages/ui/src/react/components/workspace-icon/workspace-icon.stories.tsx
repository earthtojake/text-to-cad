import type { Meta, StoryObj } from '@storybook/react-vite';
import * as React from 'react';
import { WorkspaceIcon, type WorkspaceIconStatus, type WorkspaceIconType } from './workspace-icon';

const meta: Meta<typeof WorkspaceIcon> = {
  title: 'Components/WorkspaceIcon',
  component: WorkspaceIcon,
  parameters: { layout: 'padded' },
};
export default meta;
type Story = StoryObj<typeof WorkspaceIcon>;

const TYPES: WorkspaceIconType[] = ['directory', 'repository', 'worktree'];
const STATUSES: WorkspaceIconStatus[] = ['active', 'idle', 'setting-up', 'tearing-down', 'error'];

const labelStyle: React.CSSProperties = {
  fontSize: 'var(--em-text-xs)',
  color: 'var(--em-foreground-muted)',
};

export const Default: Story = {
  args: {
    type: 'repository',
    status: 'active',
  },
};

export const Matrix: Story = {
  name: 'All types and statuses',
  render: () => (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `6rem repeat(${STATUSES.length}, 4rem) 4rem`,
        rowGap: '0.75rem',
        alignItems: 'center',
        justifyItems: 'center',
      }}
    >
      <span />
      {STATUSES.map((status) => (
        <span key={status} style={labelStyle}>
          {status}
        </span>
      ))}
      <span style={labelStyle}>no status</span>
      {TYPES.map((type) => (
        <React.Fragment key={type}>
          <span style={{ ...labelStyle, justifySelf: 'start' }}>{type}</span>
          {STATUSES.map((status) => (
            <WorkspaceIcon key={status} type={type} status={status} />
          ))}
          <WorkspaceIcon type={type} />
        </React.Fragment>
      ))}
    </div>
  ),
};

export const Sizes: Story = {
  render: () => (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1rem' }}>
      {['1.5rem', '2.25rem', '3rem', 48].map((size) => (
        <div
          key={String(size)}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <WorkspaceIcon type="worktree" status="active" size={size} />
          <span style={labelStyle}>{typeof size === 'number' ? `${size}px` : size}</span>
        </div>
      ))}
    </div>
  ),
};
