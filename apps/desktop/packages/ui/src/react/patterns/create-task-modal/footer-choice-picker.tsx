import { ChevronDown } from 'lucide-react';
import type { ReactNode, RefObject } from 'react';
import { Select } from '../../primitives/select';
import type {
  CreateTaskChoice,
  CreateTaskModalProps,
  CreateTaskSearchChoice,
} from './create-task-modal.types';
import type { CreateTaskOptionLike } from './create-task-options';
import {
  CreateTaskOptionState,
  availabilityReason,
  optionsFrom,
  selectedOption,
} from './create-task-options';
import { SearchableChoicePicker } from './searchable-choice-picker';
import * as styles from './create-task-modal.css';

export function FooterChoicePicker<T extends CreateTaskOptionLike>({
  label,
  icon,
  overlay,
  open,
  state,
  triggerRef,
  flexible,
  getLabel,
  getDescription,
  onQueryChange,
  onSelect,
  onRetry,
  onIntent,
}: {
  label: string;
  icon?: ReactNode;
  overlay: 'agent' | 'model' | 'effort';
  open: boolean;
  state: CreateTaskSearchChoice<T> | CreateTaskChoice<T>;
  triggerRef: RefObject<HTMLButtonElement | null>;
  flexible?: boolean;
  getLabel: (option: T) => string;
  getDescription: (option: T) => string | null;
  onQueryChange?: (query: string) => void;
  onSelect: (id: string) => void;
  onRetry: () => void;
  onIntent: CreateTaskModalProps['onIntent'];
}) {
  const selected = selectedOption(state.selection);
  const searchable = 'query' in state;
  const unavailable = availabilityReason(state.availability);

  if (overlay === 'effort') {
    return (
      <Select.Root
        open={open}
        value={selected?.id ?? null}
        onOpenChange={(nextOpen) => {
          if (!unavailable) {
            onIntent({
              type: 'overlay.changed',
              overlay: nextOpen ? { kind: 'effort' } : { kind: 'none' },
            });
          }
        }}
        onValueChange={(id) => {
          if (id && !unavailable) onSelect(id);
        }}
      >
        <Select.Trigger
          ref={triggerRef}
          size="sm"
          className={flexible ? styles.flexibleSelector : styles.selector}
          aria-label={`${label}: ${selected ? getLabel(selected) : label}`}
          aria-disabled={unavailable ? true : undefined}
          title={unavailable}
        >
          <Select.Value placeholder={label} />
        </Select.Trigger>
        <Select.Content width="content-at-least-trigger">
          <CreateTaskOptionState state={state.options} onRetry={onRetry} />
          {optionsFrom(state.options).map((option) => (
            <Select.Item
              key={option.id}
              value={option.id}
              disabled={option.availability.kind === 'unavailable'}
            >
              {getLabel(option)}
            </Select.Item>
          ))}
        </Select.Content>
      </Select.Root>
    );
  }

  if (!searchable || !onQueryChange) return null;

  return (
    <SearchableChoicePicker
      label={label}
      query={state.query}
      selection={state.selection}
      options={state.options}
      availability={state.availability}
      open={open}
      triggerRef={triggerRef}
      triggerClassName={flexible ? styles.flexibleSelector : styles.selector}
      getLabel={getLabel}
      getDescription={getDescription}
      renderTrigger={(current) => (
        <>
          {icon}
          <span className={styles.selectorText}>{current ? getLabel(current) : label}</span>
          <ChevronDown />
        </>
      )}
      onOpenChange={(nextOpen) =>
        onIntent({
          type: 'overlay.changed',
          overlay: nextOpen ? { kind: overlay } : { kind: 'none' },
        })
      }
      onQueryChange={onQueryChange}
      onSelect={onSelect}
      onRetry={onRetry}
    />
  );
}
