import { Bot, MessageCircle, Paperclip, ShieldCheck, Terminal } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Button } from '../../primitives/button';
import { Input } from '../../primitives/input';
import { Toggle } from '../../primitives/toggle';
import { CreateFromPicker } from './create-from-picker';
import type {
  CreateTaskAgentOption,
  CreateTaskBlocker,
  CreateTaskEffortOption,
  CreateTaskModalProps,
  CreateTaskModelOption,
  CreateTaskPromptHandle,
  CreateTaskPromptIntent,
} from './create-task-modal.types';
import { availabilityReason } from './create-task-options';
import { CreateTaskPrompt } from './create-task-prompt';
import { FooterChoicePicker } from './footer-choice-picker';
import { ProjectPicker } from './project-picker';
import { WorkspaceSettingsPicker } from './workspace-settings-picker';
import * as styles from './create-task-modal.css';

function graphemes(value: string): string[] {
  if (typeof Intl.Segmenter === 'function') {
    return Array.from(
      new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(value),
      ({ segment }) => segment
    );
  }
  return Array.from(value);
}

const BLOCKER_ORDER: Record<CreateTaskBlocker['target']['kind'], number> = {
  project: 0,
  'create-from': 1,
  'workspace-settings': 2,
  'task-name': 3,
  prompt: 4,
  agent: 5,
  model: 6,
  effort: 7,
  capability: 8,
  resource: 9,
};

export function CreateTaskModal({ state, onIntent }: CreateTaskModalProps) {
  const descriptionId = useId();
  const projectRef = useRef<HTMLButtonElement>(null);
  const originRef = useRef<HTMLButtonElement>(null);
  const workspaceRef = useRef<HTMLButtonElement>(null);
  const taskNameRef = useRef<HTMLInputElement>(null);
  const agentRef = useRef<HTMLButtonElement>(null);
  const modelRef = useRef<HTMLButtonElement>(null);
  const effortRef = useRef<HTMLButtonElement>(null);
  const autoApproveRef = useRef<HTMLButtonElement>(null);
  const tuiRef = useRef<HTMLButtonElement>(null);
  const guiRef = useRef<HTMLButtonElement>(null);
  const attachmentRef = useRef<HTMLButtonElement>(null);
  const promptRef = useRef<CreateTaskPromptHandle>(null);
  const didFocusPromptRef = useRef(false);
  const [blockedAttempt, setBlockedAttempt] = useState(0);

  useEffect(() => {
    if (didFocusPromptRef.current || state.prompt.editability.kind !== 'editable') return;
    promptRef.current?.focus();
    didFocusPromptRef.current = true;
  }, [state.prompt.editability.kind]);

  const focusBlocker = (blocker: CreateTaskBlocker) => {
    switch (blocker.target.kind) {
      case 'project':
        projectRef.current?.focus();
        return;
      case 'create-from':
        originRef.current?.focus();
        return;
      case 'workspace-settings':
        workspaceRef.current?.focus();
        return;
      case 'task-name':
        taskNameRef.current?.focus();
        return;
      case 'prompt':
      case 'resource':
        promptRef.current?.focus();
        return;
      case 'agent':
        agentRef.current?.focus();
        return;
      case 'model':
        modelRef.current?.focus();
        return;
      case 'effort':
        effortRef.current?.focus();
        return;
      case 'capability': {
        const target = {
          'auto-approve': autoApproveRef,
          tui: tuiRef,
          gui: guiRef,
          attachment: attachmentRef,
        }[blocker.target.control];
        target.current?.focus();
      }
    }
  };

  const sortedBlockers =
    state.create.kind === 'unavailable'
      ? [...state.create.blockers].sort(
          (left, right) => BLOCKER_ORDER[left.target.kind] - BLOCKER_ORDER[right.target.kind]
        )
      : [];
  const firstBlocker = sortedBlockers[0];

  const attemptCreate = () => {
    if (state.create.kind === 'available') {
      onIntent({ type: 'create.requested' });
      return;
    }
    if (firstBlocker) {
      focusBlocker(firstBlocker);
      setBlockedAttempt((attempt) => attempt + 1);
    }
  };

  const handlePromptIntent = (intent: CreateTaskPromptIntent) => {
    if (intent.type === 'prompt.create-attempted') {
      attemptCreate();
      return;
    }
    if (intent.type === 'prompt.completion-open-changed') {
      onIntent({
        type: 'overlay.changed',
        overlay: intent.open ? { kind: 'saved-prompts' } : { kind: 'none' },
      });
      return;
    }
    onIntent(intent);
  };

  const nameValue = state.taskName.value;
  const namePlaceholder =
    state.taskName.kind === 'suggested'
      ? state.taskName.suggestion
      : state.taskName.kind === 'generating'
        ? 'Generating task name…'
        : state.taskName.kind === 'generation-error'
          ? 'Task name…'
          : (state.taskName.suggestion ?? 'Task name…');

  const agentOpen = state.overlay.kind === 'agent';
  const modelOpen = state.overlay.kind === 'model';
  const effortOpen = state.overlay.kind === 'effort';

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <ProjectPicker
          state={state.project}
          open={state.overlay.kind === 'project'}
          triggerRef={projectRef}
          onIntent={onIntent}
        />
        <div className={styles.headerEnd}>
          <CreateFromPicker
            state={state.origin}
            open={state.overlay.kind === 'create-from'}
            nested={state.overlay.kind === 'create-from' ? state.overlay.nested : 'none'}
            triggerRef={originRef}
            onIntent={onIntent}
          />
          <WorkspaceSettingsPicker
            state={state.workspace}
            open={state.overlay.kind === 'workspace-settings'}
            nested={state.overlay.kind === 'workspace-settings' ? state.overlay.nested : 'none'}
            triggerRef={workspaceRef}
            onIntent={onIntent}
          />
        </div>
      </div>

      <div className={styles.taskName}>
        <label htmlFor={`${descriptionId}-task-name-input`} className={styles.taskNameLabel}>
          Task name
        </label>
        <div className={styles.taskNameControl}>
          <Input
            id={`${descriptionId}-task-name-input`}
            ref={taskNameRef}
            bare
            className={styles.taskNameInput}
            value={nameValue}
            placeholder={namePlaceholder}
            aria-label="Task name"
            aria-describedby={
              state.taskName.kind === 'suggested'
                ? `${descriptionId}-task-name-description`
                : state.taskName.kind === 'generation-error'
                  ? `${descriptionId}-task-name-error`
                  : undefined
            }
            onChange={(event) => {
              const segments = graphemes(event.target.value);
              const value = segments.slice(0, 256).join('');
              onIntent({
                type: 'task-name.changed',
                value,
                wasTruncated: segments.length > 256,
              });
            }}
          />
          {state.taskName.kind === 'generation-error' && (
            <span id={`${descriptionId}-task-name-error`} className={styles.taskNameError}>
              <span>{state.taskName.message}</span>
              {state.taskName.retryable && (
                <Button
                  size="xs"
                  aria-label="Retry Task name generation"
                  onClick={() => onIntent({ type: 'task-name.generation-retry-requested' })}
                >
                  Retry
                </Button>
              )}
            </span>
          )}
        </div>
        {state.taskName.kind === 'suggested' && (
          <span id={`${descriptionId}-task-name-description`} className={styles.visuallyHidden}>
            Leave empty to use {state.taskName.suggestion}.
          </span>
        )}
      </div>

      <CreateTaskPrompt
        ref={promptRef}
        state={{
          ...state.prompt,
          completionOpen: state.overlay.kind === 'saved-prompts',
        }}
        onIntent={handlePromptIntent}
      />

      <div className={styles.footer}>
        <div className={styles.footerStart}>
          <FooterChoicePicker
            label="Agent"
            icon={<Bot />}
            overlay="agent"
            open={agentOpen}
            state={state.run.agent}
            triggerRef={agentRef}
            flexible
            getLabel={(agent: CreateTaskAgentOption) => agent.label}
            getDescription={(agent: CreateTaskAgentOption) => agent.description}
            onQueryChange={(query) => onIntent({ type: 'run.agent-query-changed', query })}
            onSelect={(agentId) => onIntent({ type: 'run.agent-selected', agentId })}
            onRetry={() => onIntent({ type: 'run.agent-retry-requested' })}
            onIntent={onIntent}
          />
          <FooterChoicePicker
            label="Model"
            overlay="model"
            open={modelOpen}
            state={state.run.model}
            triggerRef={modelRef}
            flexible
            getLabel={(model: CreateTaskModelOption) => model.label}
            getDescription={(model: CreateTaskModelOption) => model.description}
            onQueryChange={(query) => onIntent({ type: 'run.model-query-changed', query })}
            onSelect={(modelId) => onIntent({ type: 'run.model-selected', modelId })}
            onRetry={() => onIntent({ type: 'run.model-retry-requested' })}
            onIntent={onIntent}
          />
          <FooterChoicePicker
            label="Effort"
            overlay="effort"
            open={effortOpen}
            state={state.run.effort}
            triggerRef={effortRef}
            flexible
            getLabel={(effort: CreateTaskEffortOption) => effort.label}
            getDescription={(effort: CreateTaskEffortOption) => effort.description}
            onSelect={(effortId) => onIntent({ type: 'run.effort-selected', effortId })}
            onRetry={() => onIntent({ type: 'run.effort-retry-requested' })}
            onIntent={onIntent}
          />
          <Toggle
            ref={autoApproveRef}
            icon
            size="sm"
            aria-label={`Auto-approve ${state.run.autoApprove.kind === 'supported' && state.run.autoApprove.value ? 'enabled' : 'disabled'}`}
            aria-pressed={
              state.run.autoApprove.kind === 'supported' ? state.run.autoApprove.value : false
            }
            aria-disabled={state.run.autoApprove.kind === 'unsupported' ? true : undefined}
            title={
              state.run.autoApprove.kind === 'unsupported'
                ? state.run.autoApprove.reason
                : 'Toggle auto-approve'
            }
            onClick={() => {
              if (state.run.autoApprove.kind === 'supported') {
                onIntent({
                  type: 'run.auto-approve-changed',
                  value: !state.run.autoApprove.value,
                });
              }
            }}
          >
            <ShieldCheck />
          </Toggle>
          <div className={styles.radioDock} role="radiogroup" aria-label="Conversation interface">
            {(['tui', 'gui'] as const).map((mode) => {
              const availability = state.run.conversationInterface.availability[mode];
              const unavailable = availabilityReason(availability);
              return (
                <Toggle
                  key={mode}
                  ref={mode === 'tui' ? tuiRef : guiRef}
                  icon
                  size="sm"
                  role="radio"
                  aria-label={mode === 'tui' ? 'TUI' : 'GUI'}
                  aria-checked={state.run.conversationInterface.value === mode}
                  pressed={state.run.conversationInterface.value === mode}
                  aria-disabled={unavailable ? true : undefined}
                  title={unavailable}
                  onClick={() => {
                    if (!unavailable) {
                      onIntent({ type: 'run.conversation-interface-changed', value: mode });
                    }
                  }}
                >
                  {mode === 'tui' ? <Terminal /> : <MessageCircle />}
                </Toggle>
              );
            })}
          </div>
        </div>
        <div className={styles.footerEnd}>
          <Button
            ref={attachmentRef}
            icon
            size="sm"
            aria-label="Attach files"
            aria-disabled={state.prompt.intake.kind === 'unavailable' ? true : undefined}
            title={availabilityReason(state.prompt.intake)}
            onClick={() => {
              if (state.prompt.intake.kind === 'available') {
                onIntent({
                  type: 'prompt.attachment-picker-requested',
                  insertion: promptRef.current?.getInsertion() ?? {
                    baseValue: state.prompt.value,
                    range: { from: state.prompt.value.length, to: state.prompt.value.length },
                  },
                });
              }
            }}
          >
            <Paperclip />
          </Button>
          <Button
            variant="primary"
            size="sm"
            aria-label="Create"
            aria-disabled={state.create.kind === 'unavailable' ? true : undefined}
            aria-describedby={
              state.create.kind === 'unavailable' ? `${descriptionId}-create-blockers` : undefined
            }
            title={firstBlocker?.message}
            onClick={attemptCreate}
          >
            Create
          </Button>
        </div>
      </div>

      {state.create.kind === 'unavailable' && (
        <span id={`${descriptionId}-create-blockers`} className={styles.visuallyHidden}>
          {sortedBlockers.map((blocker) => blocker.message).join(' ')}
        </span>
      )}
      <div className={styles.visuallyHidden} aria-live="polite" role="status">
        {state.announcements.polite?.text}
      </div>
      <div className={styles.visuallyHidden} aria-live="assertive" role="alert">
        {state.announcements.assertive?.text ??
          (blockedAttempt > 0 && state.create.kind === 'unavailable' ? (
            <span key={blockedAttempt}>
              {sortedBlockers.map((blocker) => blocker.message).join(' ')}
            </span>
          ) : null)}
      </div>
    </div>
  );
}
