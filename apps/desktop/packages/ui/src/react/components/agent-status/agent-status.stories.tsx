import { Tooltip } from '@react/primitives/tooltip';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { AgentStatus, type AgentStatusKind } from './agent-status';
import { BrailleSpinner, type BrailleSpinnerVariant } from './braille-spinner';

const STATUSES: Array<{ label: string; status: AgentStatusKind }> = [
  { label: 'Working', status: 'working' },
  { label: 'Awaiting Input', status: 'awaiting-input' },
  { label: 'Error', status: 'error' },
  { label: 'Completed', status: 'completed' },
  { label: 'Idle (renders nothing)', status: 'idle' },
];

const ACTIVE_STATUSES = STATUSES.filter(({ status }) => status !== 'idle');

const meta: Meta<typeof AgentStatus> = {
  title: 'Components/AgentStatus',
  component: AgentStatus,
  parameters: { layout: 'centered' },
  args: {
    status: 'working',
    size: '2rem',
  },
};
export default meta;
type Story = StoryObj<typeof AgentStatus>;

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
            <AgentStatus status={status} size="2rem" />
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

export const WithTooltip: Story = {
  name: 'With tooltip',
  render: () => (
    <Tooltip.Provider>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
        {ACTIVE_STATUSES.map(({ status }) => (
          <AgentStatus key={status} status={status} size="2rem" tooltip />
        ))}
      </div>
    </Tooltip.Provider>
  ),
};

export const Sizes: Story = {
  name: 'Sizes',
  render: () => (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '2rem',
      }}
    >
      {ACTIVE_STATUSES.map(({ label, status }) => (
        <div key={status}>
          <span
            style={{
              display: 'block',
              fontSize: 'var(--em-text-xs)',
              fontWeight: 400,
              color: 'var(--em-foreground-muted)',
              marginBottom: '0.75rem',
              fontFamily: 'var(--em-font-mono)',
            }}
          >
            {label}
          </span>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1.5rem' }}>
            {['1rem', '1.5rem', '2rem', '2.5rem'].map((size) => (
              <div
                key={size}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <AgentStatus status={status} size={size} />
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

export const SpinnerVariants: Story = {
  name: 'Braille spinner variants',
  render: () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '2.5rem' }}>
      {(['dots', 'wave'] satisfies BrailleSpinnerVariant[]).map((variant) => (
        <div
          key={variant}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.75rem',
            fontSize: 'var(--em-text-lg)',
          }}
        >
          <BrailleSpinner variant={variant} />
          <span
            style={{
              fontFamily: 'var(--em-font-mono)',
              fontSize: 'var(--em-text-xs)',
              color: 'var(--em-foreground-muted)',
            }}
          >
            {variant}
          </span>
        </div>
      ))}
    </div>
  ),
};
