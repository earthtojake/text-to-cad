import type { Meta, StoryObj } from '@storybook/react-vite';
import * as React from 'react';
import { Button } from '../../primitives/button';
import { SteppedLoader, SteppedLoaderProgress, type StepStatus } from './stepped-loader';

const BASE_STEPS = [
  { id: 'clone', name: 'Clone repository' },
  { id: 'install', name: 'Install dependencies' },
  { id: 'configure', name: 'Configure workspace' },
  { id: 'start', name: 'Start development server' },
];

const meta: Meta<typeof SteppedLoader> = {
  title: 'Components/SteppedLoader',
  component: SteppedLoader,
  parameters: { layout: 'centered' },
  args: {
    steps: BASE_STEPS,
    activeStepId: 'install',
    status: 'loading',
    actions: cancelAction(),
  },
  argTypes: {
    status: {
      control: 'select',
      options: ['pending', 'loading', 'error'],
    },
  },
};
export default meta;
type Story = StoryObj<typeof SteppedLoader>;

/**
 * Tall fixed-height frame so the floating footer visibly sinks to the bottom
 * while the header/children stay pinned to the top.
 */
function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        width: '24rem',
        height: '30rem',
        padding: '1rem',
        border: '1px dashed var(--em-border)',
        borderRadius: 'var(--em-radius-lg)',
        boxSizing: 'border-box',
      }}
    >
      {children}
    </div>
  );
}

/** Single ghost Cancel button — the default footer action ([ 2/4 ─── Cancel ]). */
function cancelAction() {
  return (
    <Button size="xs" variant="ghost">
      Cancel
    </Button>
  );
}

function retryCancelActions() {
  return (
    <>
      <Button size="xs" variant="ghost">
        Retry
      </Button>
      <Button size="xs" variant="ghost">
        Cancel
      </Button>
    </>
  );
}

/** Attaches a progress-bar child to the `install` step at the given percent. */
function withInstallProgress(percent: number) {
  return BASE_STEPS.map((step) =>
    step.id === 'install'
      ? {
          ...step,
          children: (
            <SteppedLoaderProgress
              percent={percent}
              aria-label="Install progress"
              leftLabel="Install progress"
              rightLabel="54%"
            />
          ),
        }
      : step
  );
}

export const Loading: Story = {
  name: 'Loading (footer + cancel)',
  args: {
    status: 'loading',
  },
  render: (args) => (
    <Frame>
      <SteppedLoader {...args} />
    </Frame>
  ),
};

export const LoadingWithProgress: Story = {
  name: 'Loading with progress child',
  args: {
    status: 'loading',
    steps: withInstallProgress(42),
  },
  render: (args) => (
    <Frame>
      <SteppedLoader {...args} />
    </Frame>
  ),
};

export const ErrorState: Story = {
  name: 'Error (retry + cancel)',
  args: {
    status: 'error',
    actions: retryCancelActions(),
  },
  render: (args) => (
    <Frame>
      <SteppedLoader {...args} />
    </Frame>
  ),
};

export const WithoutActions: Story = {
  name: 'Without actions (footer shows progress only)',
  args: {
    status: 'loading',
    actions: undefined,
  },
  render: (args) => (
    <Frame>
      <SteppedLoader {...args} />
    </Frame>
  ),
};

// ── Footer step counter: same loader at each step (1/4 → 4/4) ──────────────────

export const StepProgression: Story = {
  name: 'Step progression (footer counter)',
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '24rem' }}>
      {BASE_STEPS.map((step) => (
        <SteppedLoader
          key={step.id}
          steps={BASE_STEPS}
          activeStepId={step.id}
          status="loading"
          actions={cancelAction()}
        />
      ))}
    </div>
  ),
};

const ALL_STATES: Array<{
  label: string;
  status: StepStatus;
  percent?: number;
  actions?: boolean;
}> = [
  { label: 'pending', status: 'pending' },
  { label: 'loading', status: 'loading' },
  { label: 'loading 42%', status: 'loading', percent: 42 },
  { label: 'error', status: 'error', actions: true },
];

export const AllStates: Story = {
  name: 'All states',
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '28rem' }}>
      {ALL_STATES.map(({ label, status, percent, actions }) => (
        <div key={label}>
          <p
            style={{
              fontSize: 'var(--em-text-xs)',
              color: 'var(--em-foreground-muted)',
              marginBottom: '0.375rem',
              fontFamily: 'var(--em-font-mono)',
            }}
          >
            {label}
          </p>
          <SteppedLoader
            steps={percent != null ? withInstallProgress(percent) : BASE_STEPS}
            activeStepId="install"
            status={status}
            actions={actions ? retryCancelActions() : cancelAction()}
          />
        </div>
      ))}
    </div>
  ),
};

function InteractiveDemo() {
  const [activeIndex, setActiveIndex] = React.useState(0);
  const [status, setStatus] = React.useState<StepStatus>('loading');
  const [progress, setProgress] = React.useState(0);
  const [isRunning, setIsRunning] = React.useState(true);
  const isLastStep = activeIndex >= BASE_STEPS.length - 1;
  const activeStep = BASE_STEPS[activeIndex] ?? BASE_STEPS[0];
  const activeStepId = activeStep?.id ?? 'clone';

  React.useEffect(() => {
    if (!isRunning || status !== 'loading') {
      return;
    }

    // When the current step finishes, advance straight to the next step; the
    // loader plays its slide transition. No intermediate success state.
    if (progress >= 100) {
      if (isLastStep) {
        return;
      }

      const timer = window.setTimeout(() => {
        setActiveIndex((current) => Math.min(BASE_STEPS.length - 1, current + 1));
        setProgress(0);
      }, 400);

      return () => window.clearTimeout(timer);
    }

    const timer = window.setTimeout(() => {
      setProgress((current) => Math.min(100, current + 12));
    }, 250);

    return () => window.clearTimeout(timer);
  }, [isLastStep, isRunning, progress, status]);

  function retry() {
    setIsRunning(true);
    setProgress(0);
    setStatus('loading');
  }

  function cancel() {
    setIsRunning(false);
    setStatus('pending');
  }

  function triggerError() {
    setIsRunning(false);
    setStatus('error');
  }

  function reset() {
    setActiveIndex(0);
    setProgress(0);
    setStatus('loading');
    setIsRunning(true);
  }

  const steps = BASE_STEPS.map((step, index) => ({
    ...step,
    children:
      index <= activeIndex ? (
        <SteppedLoaderProgress
          percent={index < activeIndex ? 100 : progress}
          aria-label={`${step.name} progress`}
          leftLabel={step.name}
          rightLabel={`${index < activeIndex ? 100 : progress}%`}
        />
      ) : undefined,
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '24rem' }}>
      <Frame>
        <SteppedLoader
          steps={steps}
          activeStepId={activeStepId}
          status={status}
          actions={
            <>
              <Button size="xs" variant="ghost" onClick={retry}>
                Retry
              </Button>
              <Button size="xs" variant="ghost" onClick={triggerError}>
                Error
              </Button>
              <Button size="xs" variant="ghost" onClick={cancel}>
                Cancel
              </Button>
            </>
          }
        />
      </Frame>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Button size="xs" variant="ghost" onClick={reset}>
          Reset demo
        </Button>
        <span
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-passive)',
            fontFamily: 'var(--em-font-mono)',
          }}
        >
          status: {status}
        </span>
      </div>
    </div>
  );
}

export const Interactive: Story = {
  name: 'Interactive walkthrough',
  render: () => <InteractiveDemo />,
};
