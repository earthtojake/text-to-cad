import type { Meta, StoryObj } from '@storybook/react-vite';
import { ScriptStatus, type ScriptStatusKind } from './script-status';

const STATUSES: Array<{ label: string; status: ScriptStatusKind }> = [
  { label: 'Success', status: 'success' },
  { label: 'Error', status: 'error' },
  { label: 'In Progress', status: 'in-progress' },
  { label: 'Waiting', status: 'waiting' },
];

const SIZES = ['1rem', '1.5rem', '2rem', '2.5rem'];

const meta: Meta<typeof ScriptStatus> = {
  title: 'Components/ScriptStatus',
  component: ScriptStatus,
  parameters: { layout: 'centered' },
  args: {
    status: 'in-progress',
    size: '2rem',
  },
};
export default meta;
type Story = StoryObj<typeof ScriptStatus>;

export const Default: Story = {
  name: 'Default',
};

export const AllStates: Story = {
  name: 'All states',
  render: () => (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1.5rem' }}>
      {STATUSES.map(({ label, status }) => (
        <div
          key={status}
          style={{
            display: 'flex',
            minWidth: '7rem',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.75rem',
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              width: '2.5rem',
              height: '2.5rem',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px dashed var(--em-border)',
              borderRadius: 'var(--em-radius-md)',
            }}
          >
            <ScriptStatus status={status} size="2rem" />
          </div>
          <span
            style={{
              maxWidth: '7rem',
              textAlign: 'center',
              fontSize: 'var(--em-text-xs)',
              lineHeight: 'var(--em-text-xs--line-height)',
              color: 'var(--em-foreground-muted)',
            }}
          >
            {label}
          </span>
        </div>
      ))}
    </div>
  ),
};

export const Sizes: Story = {
  name: 'Sizes',
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {STATUSES.map(({ label, status }) => (
        <div key={status}>
          <span
            style={{
              display: 'block',
              marginBottom: '0.75rem',
              fontFamily: 'var(--em-font-mono)',
              fontSize: 'var(--em-text-xs)',
              fontWeight: 400,
              color: 'var(--em-foreground-muted)',
            }}
          >
            {label}
          </span>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1.5rem' }}>
            {SIZES.map((size) => (
              <div
                key={size}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <ScriptStatus status={status} size={size} />
                <span
                  style={{
                    fontFamily: 'var(--em-font-mono)',
                    fontSize: 'var(--em-text-xs)',
                    color: 'var(--em-foreground-muted)',
                  }}
                >
                  {size}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  ),
};
