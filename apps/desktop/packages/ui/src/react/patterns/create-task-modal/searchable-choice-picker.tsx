import type { ReactNode, RefObject } from 'react';
import { Button } from '../../primitives/button';
import { Combobox } from '../../primitives/combobox/combobox';
import type {
  CreateTaskAvailability,
  CreateTaskOptionsState,
  CreateTaskSelection,
} from './create-task-modal.types';
import type { CreateTaskOptionLike } from './create-task-options';
import {
  CreateTaskOptionState,
  availabilityReason,
  optionsFrom,
  selectedOption,
} from './create-task-options';
import * as styles from './create-task-modal.css';

export function SearchableChoicePicker<T extends CreateTaskOptionLike>({
  label,
  query,
  selection,
  options,
  availability = { kind: 'available' },
  open,
  triggerRef,
  triggerClassName,
  renderTrigger,
  getLabel,
  getDescription,
  renderFooter,
  onOpenChange,
  onQueryChange,
  onSelect,
  onRetry,
}: {
  label: string;
  query: string;
  selection: CreateTaskSelection<T>;
  options: CreateTaskOptionsState<T>;
  availability?: CreateTaskAvailability;
  open: boolean;
  triggerRef: RefObject<HTMLButtonElement | null>;
  triggerClassName?: string;
  renderTrigger: (selected: T | null) => ReactNode;
  getLabel: (option: T) => string;
  getDescription?: (option: T) => ReactNode;
  renderFooter?: () => ReactNode;
  onOpenChange: (open: boolean) => void;
  onQueryChange: (query: string) => void;
  onSelect: (id: string) => void;
  onRetry: () => void;
}) {
  const selected = selectedOption(selection);
  const items = [...optionsFrom(options)];
  const unavailable = availabilityReason(availability);

  return (
    <Combobox.Root
      items={items}
      value={selected}
      open={open}
      inputValue={query}
      onOpenChange={(nextOpen) => {
        if (!unavailable) onOpenChange(nextOpen);
      }}
      onInputValueChange={(nextQuery) => onQueryChange(nextQuery)}
      onValueChange={(option: T | null) => {
        if (option && option.availability.kind === 'available' && !unavailable) {
          onSelect(option.id);
        }
      }}
      isItemEqualToValue={(left: T, right: T) => left.id === right.id}
      filter={() => true}
      autoHighlight
    >
      <Combobox.Trigger
        render={
          <Button
            ref={triggerRef}
            size="sm"
            className={triggerClassName}
            aria-label={`${label}: ${selected ? getLabel(selected) : label}`}
            aria-disabled={unavailable ? true : undefined}
            title={unavailable}
            onClick={(event) => {
              if (unavailable) event.preventDefault();
            }}
          />
        }
      >
        {renderTrigger(selected)}
      </Combobox.Trigger>
      <Combobox.Content width="content-at-least-trigger">
        <div className={styles.comboboxHeader}>{label}</div>
        <Combobox.Input
          showTrigger={false}
          aria-label={`Search ${label}`}
          placeholder={`Search ${label}…`}
        />
        <CreateTaskOptionState state={options} onRetry={onRetry} />
        {items.length > 0 && (
          <Combobox.List>
            {items.map((option) => (
              <Combobox.Item
                key={option.id}
                value={option}
                disabled={option.availability.kind === 'unavailable'}
                title={availabilityReason(option.availability)}
              >
                <span className={styles.itemContent}>
                  <span className={styles.itemLabel}>{getLabel(option)}</span>
                  {getDescription && (
                    <span className={styles.itemDescription}>{getDescription(option)}</span>
                  )}
                </span>
              </Combobox.Item>
            ))}
          </Combobox.List>
        )}
        {renderFooter && <div className={styles.comboboxFooter}>{renderFooter()}</div>}
      </Combobox.Content>
    </Combobox.Root>
  );
}
