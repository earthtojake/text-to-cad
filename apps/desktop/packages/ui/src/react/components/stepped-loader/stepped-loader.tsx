import { SegmentedSpinnerIcon } from '@react/primitives/segmented-spinner';
import { cx } from '@styles/utilities/cx';
import { AlertCircleIcon, CircleIcon } from 'lucide-react';
import * as React from 'react';
import * as styles from './stepped-loader.css';

export type StepStatus = 'pending' | 'loading' | 'error';

export interface SteppedLoaderStep {
  id: string;
  name: string;
  /** Optional per-step content rendered under the step row, e.g. a progress bar. */
  children?: React.ReactNode;
}

export interface SteppedLoaderProps {
  steps: SteppedLoaderStep[];
  activeStepId: string;
  /** Status shown for the active step. */
  status: StepStatus;
  /** Rendered under the divider, e.g. retry/cancel buttons. */
  actions?: React.ReactNode;
  className?: string;
}

type PresentationPhase = 'idle' | 'exiting' | 'entering';

interface PresentationState {
  stepId: string;
  status: StepStatus;
  phase: PresentationPhase;
}

const EXIT_MS = 220;
const ENTER_MS = 180;

const ICON_SIZE: React.CSSProperties = { width: '1.25rem', height: '1.25rem', flexShrink: 0 };

function clampPercent(percent: number) {
  return Math.max(0, Math.min(100, Math.round(percent)));
}

export interface SteppedLoaderProgressProps {
  percent: number;
  'aria-label'?: string;
  leftLabel: string;
  rightLabel: string;
}

function SteppedLoaderProgress({
  percent,
  'aria-label': ariaLabel,
  leftLabel,
  rightLabel,
}: SteppedLoaderProgressProps) {
  const clampedPercent = clampPercent(percent);

  return (
    <div className={styles.progressContainer}>
      <div className={styles.progressHeader}>
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
      <div className={styles.progressTrack}>
        <div
          className={styles.progressFill}
          style={{ width: `${clampedPercent}%` }}
          role="progressbar"
          aria-label={ariaLabel}
          aria-valuenow={clampedPercent}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  );
}

function SteppedLoader({ steps, activeStepId, status, actions, className }: SteppedLoaderProps) {
  const firstStepId = steps[0]?.id ?? activeStepId;
  const initialStepId = steps.some((step) => step.id === activeStepId) ? activeStepId : firstStepId;
  const [presentation, setPresentation] = React.useState<PresentationState>({
    stepId: initialStepId,
    status,
    phase: 'idle',
  });
  const presentationRef = React.useRef(presentation);
  const latestTargetRef = React.useRef({ stepId: initialStepId, status });
  const pendingTargetRef = React.useRef<{ stepId: string; status: StepStatus } | null>(null);
  const timersRef = React.useRef<number[]>([]);

  React.useEffect(() => {
    presentationRef.current = presentation;
  }, [presentation]);

  React.useEffect(() => {
    latestTargetRef.current = { stepId: initialStepId, status };
  }, [initialStepId, status]);

  React.useEffect(() => {
    return () => {
      timersRef.current.forEach((timer) => window.clearTimeout(timer));
      timersRef.current = [];
    };
  }, []);

  React.useEffect(() => {
    const current = presentationRef.current;

    if (current.stepId === initialStepId) {
      if (current.phase === 'exiting') {
        return;
      }

      setPresentation((prev) => {
        if (prev.stepId !== initialStepId || prev.phase === 'exiting') {
          return prev;
        }

        if (prev.status === status && prev.phase === 'idle') {
          return prev;
        }

        return { ...prev, status, phase: 'idle' };
      });
      return;
    }

    if (pendingTargetRef.current?.stepId === initialStepId) {
      pendingTargetRef.current.status = status;
      return;
    }

    timersRef.current.forEach((timer) => window.clearTimeout(timer));
    timersRef.current = [];
    pendingTargetRef.current = { stepId: initialStepId, status };

    // Slide the current step out immediately, then swap and slide the next in.
    setPresentation((prev) => ({ ...prev, phase: 'exiting' }));

    scheduleTimer(() => {
      const target = pendingTargetRef.current ?? latestTargetRef.current;
      pendingTargetRef.current = null;
      setPresentation({
        stepId: target.stepId,
        status: target.status,
        phase: 'entering',
      });

      scheduleTimer(() => {
        const latestTarget = latestTargetRef.current;
        setPresentation((prev) => {
          if (prev.stepId !== latestTarget.stepId) {
            return prev;
          }

          return {
            stepId: latestTarget.stepId,
            status: latestTarget.status,
            phase: 'idle',
          };
        });
      }, ENTER_MS);
    }, EXIT_MS);
  }, [initialStepId, status]);

  function scheduleTimer(callback: () => void, delay: number) {
    const timer = window.setTimeout(callback, delay);
    timersRef.current.push(timer);
  }

  if (steps.length === 0) {
    return null;
  }

  const displayedStep = steps.find((step) => step.id === presentation.stepId) ?? steps[0];
  const activeIndex = steps.findIndex((step) => step.id === activeStepId);
  const currentStepNumber = activeIndex >= 0 ? activeIndex + 1 : 1;

  return (
    <div className={cx(styles.root, className)}>
      <div className={styles.stepViewport}>
        <div
          className={cx(
            styles.stepRow,
            presentation.phase === 'exiting' && styles.stepExit,
            presentation.phase === 'entering' && styles.stepEnter
          )}
        >
          <StatusIcon status={presentation.status} />
          <span className={styles.stepName}>{displayedStep.name}</span>
        </div>
      </div>
      {displayedStep.children && (
        <div className={styles.stepChildren}>{displayedStep.children}</div>
      )}
      {(steps.length > 1 || actions) && (
        <div className={styles.footer}>
          <span className={styles.footerProgress}>
            {currentStepNumber}/{steps.length}
          </span>
          {actions && <div className={styles.footerActions}>{actions}</div>}
        </div>
      )}
    </div>
  );
}

function StatusIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case 'loading':
      return (
        <span className={cx(styles.iconSlot, styles.iconLoading)} aria-label="Loading">
          <SegmentedSpinnerIcon style={ICON_SIZE} />
        </span>
      );
    case 'error':
      return (
        <span className={cx(styles.iconSlot, styles.iconError)} aria-label="Error">
          <AlertCircleIcon style={ICON_SIZE} />
        </span>
      );
    case 'pending':
    default:
      return (
        <span className={cx(styles.iconSlot, styles.iconPending)} aria-label="Pending">
          <CircleIcon style={ICON_SIZE} />
        </span>
      );
  }
}

export { SteppedLoader, SteppedLoaderProgress };
