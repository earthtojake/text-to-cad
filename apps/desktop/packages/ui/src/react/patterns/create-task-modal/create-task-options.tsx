import { RotateCw } from 'lucide-react';
import { Button } from '../../primitives/button';
import { Spinner } from '../../primitives/spinner';
import type {
  CreateTaskAvailability,
  CreateTaskOptionAvailability,
  CreateTaskOptionsState,
  CreateTaskSelection,
} from './create-task-modal.types';
import * as styles from './create-task-modal.css';

export type CreateTaskOptionLike = {
  id: string;
  availability: CreateTaskOptionAvailability;
};

export function selectedOption<T>(selection: CreateTaskSelection<T>): T | null {
  return selection.kind === 'selected' ? selection.option : null;
}

export function optionsFrom<T>(state: CreateTaskOptionsState<T>): readonly T[] {
  return state.kind === 'ready' || state.kind === 'refreshing' || state.kind === 'stale-error'
    ? state.items
    : [];
}

export function availabilityReason(availability: CreateTaskAvailability): string | undefined {
  return availability.kind === 'unavailable' ? availability.reason : undefined;
}

export function CreateTaskOptionState({
  state,
  onRetry,
}: {
  state: CreateTaskOptionsState<unknown>;
  onRetry?: () => void;
}) {
  if (state.kind === 'loading') {
    return (
      <div className={styles.state} aria-busy="true">
        <Spinner />
        <span>Loading…</span>
      </div>
    );
  }
  if (state.kind === 'empty') return <div className={styles.state}>No results</div>;
  if (state.kind === 'unavailable') {
    return <div className={styles.state}>{state.reason}</div>;
  }
  if (state.kind === 'error') {
    return (
      <div className={styles.state} role="alert">
        <span>{state.message}</span>
        {state.retryable && onRetry && (
          <Button size="sm" onClick={onRetry}>
            <RotateCw />
            Retry
          </Button>
        )}
      </div>
    );
  }
  if (state.kind === 'stale-error') {
    return (
      <div className={styles.notice} role="alert">
        {state.message}
        {state.retryable && onRetry && (
          <Button size="xs" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    );
  }
  return null;
}
