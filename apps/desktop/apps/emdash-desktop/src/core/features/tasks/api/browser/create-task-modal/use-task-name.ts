import { useCallback, useState } from 'react';
import { liveTransformTaskName } from '@core/features/tasks/api/browser/taskNames';

export type TaskNameState = {
  /** The user's typed value — may be empty if they haven't typed anything yet. */
  taskName: string;
  /** The generated name shown as placeholder when the input is empty. */
  placeholder: string;
  /** The name to use when creating: the user's value if non-empty, else the generated name. */
  effectiveTaskName: string;
  handleTaskNameChange: (value: string) => void;
  showSlugHint: boolean;
  isPending: boolean;
};

export function useTaskName(opts?: {
  generatedName?: string;
  isPending?: boolean;
  resetKey?: unknown;
  initialName?: string;
}): TaskNameState {
  const { generatedName, isPending = false, resetKey } = opts ?? {};
  const [taskName, setTaskName] = useState('');
  const [showSlugHint, setShowSlugHint] = useState(false);
  const [prevResetKey, setPrevResetKey] = useState(resetKey);

  // Reset user input when the project/context changes.
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey);
    setTaskName('');
    setShowSlugHint(false);
  }

  const handleTaskNameChange = useCallback((value: string) => {
    const transformed = liveTransformTaskName(value);
    setTaskName(transformed);
    const hasDroppedChars = /[^a-z0-9\s-]/i.test(value);
    setShowSlugHint(hasDroppedChars);
  }, []);

  const placeholder = generatedName ?? '';
  const effectiveTaskName = taskName.trim() || generatedName || '';

  return {
    taskName,
    placeholder,
    effectiveTaskName,
    handleTaskNameChange,
    showSlugHint,
    isPending,
  };
}
