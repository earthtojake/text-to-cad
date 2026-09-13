import { ChevronDown, GitBranch } from 'lucide-react';
import type { ReactNode, RefObject } from 'react';
import { Button } from '../../primitives/button';
import { Combobox } from '../../primitives/combobox/combobox';
import { Popover } from '../../primitives/popover';
import { Select } from '../../primitives/select';
import { Tabs } from '../../primitives/tabs/tabs';
import type {
  CreateTaskModalProps,
  CreateTaskOptionsState,
  CreateTaskOriginState,
} from './create-task-modal.types';
import type { CreateTaskOptionLike } from './create-task-options';
import {
  CreateTaskOptionState,
  availabilityReason,
  optionsFrom,
  selectedOption,
} from './create-task-options';
import * as styles from './create-task-modal.css';

function InlineOriginOptions<T extends CreateTaskOptionLike>({
  label,
  query,
  state,
  selectedId,
  getLabel,
  getDescription,
  onQueryChange,
  onSelect,
  onRetry,
}: {
  label: string;
  query: string;
  state: CreateTaskOptionsState<T>;
  selectedId?: string;
  getLabel: (option: T) => string;
  getDescription?: (option: T) => ReactNode;
  onQueryChange: (query: string) => void;
  onSelect: (id: string) => void;
  onRetry: () => void;
}) {
  const items = [...optionsFrom(state)];
  const selected = items.find((option) => option.id === selectedId) ?? null;
  return (
    <Combobox.Root
      items={items}
      value={selected}
      inputValue={query}
      onInputValueChange={(nextQuery) => onQueryChange(nextQuery)}
      onValueChange={(option: T | null) => {
        if (option?.availability.kind === 'available') onSelect(option.id);
      }}
      isItemEqualToValue={(left: T, right: T) => left.id === right.id}
      filter={() => true}
      autoHighlight
    >
      <Combobox.Input
        showTrigger={false}
        aria-label={`Search ${label}`}
        placeholder={`Search ${label}…`}
      />
      <div className={styles.popupBody}>
        <CreateTaskOptionState state={state} onRetry={onRetry} />
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
      </div>
    </Combobox.Root>
  );
}

function originSummary(state: CreateTaskOriginState): string {
  if (state.selection.kind === 'unlinked') return 'Create from…';
  const { origin } = state.selection;
  if (origin.kind === 'branch') return `Branch: ${origin.option.label}`;
  if (origin.kind === 'issue') return `Issue: ${origin.option.identifier}`;
  return `PR: #${origin.option.number}`;
}

export function CreateFromPicker({
  state,
  open,
  nested,
  triggerRef,
  onIntent,
}: {
  state: CreateTaskOriginState;
  open: boolean;
  nested: 'none' | 'issue-provider' | 'pull-request-status';
  triggerRef: RefObject<HTMLButtonElement | null>;
  onIntent: CreateTaskModalProps['onIntent'];
}) {
  const active = state.activeKind === 'pull-request' ? state.pullRequest : state[state.activeKind];
  const selectedId =
    state.selection.kind === 'linked' ? state.selection.origin.option.id : undefined;
  return (
    <Popover.Root
      open={open}
      onOpenChange={(nextOpen) =>
        onIntent({
          type: 'overlay.changed',
          overlay: nextOpen ? { kind: 'create-from', nested: 'none' } : { kind: 'none' },
        })
      }
    >
      <Popover.Trigger
        render={
          <Button
            ref={triggerRef}
            size="sm"
            className={styles.selector}
            aria-label={originSummary(state)}
          />
        }
      >
        <GitBranch />
        <span className={styles.selectorText}>{originSummary(state)}</span>
        <ChevronDown />
      </Popover.Trigger>
      <Popover.Content align="end" className={styles.popup}>
        <div className={styles.popupHeader}>
          <Popover.Title>Create From</Popover.Title>
          {state.selection.kind === 'linked' && (
            <Button size="xs" onClick={() => onIntent({ type: 'origin.cleared' })}>
              Clear
            </Button>
          )}
        </div>
        <Tabs.Root
          value={state.activeKind}
          onValueChange={(kind) => {
            if (kind === 'branch' || kind === 'issue' || kind === 'pull-request') {
              onIntent({ type: 'origin.kind-changed', kind });
            }
          }}
        >
          <Tabs.List aria-label="Create From type">
            {(['branch', 'issue', 'pull-request'] as const).map((kind) => {
              const region = state[kind === 'pull-request' ? 'pullRequest' : kind];
              const unavailableReason = region.kind === 'unsupported' ? region.reason : undefined;
              const label =
                kind === 'branch' ? 'Branch' : kind === 'issue' ? 'Issue' : 'Pull Request';
              return (
                <Tabs.Tab
                  key={kind}
                  value={kind}
                  title={
                    unavailableReason ? `${label} unavailable: ${unavailableReason}` : undefined
                  }
                >
                  {label}
                </Tabs.Tab>
              );
            })}
          </Tabs.List>
        </Tabs.Root>
        {active.kind === 'unsupported' ? (
          <div className={styles.state}>{active.reason}</div>
        ) : (
          <>
            {state.activeKind === 'issue' && state.issue.kind === 'available' && (
              <>
                <CreateTaskOptionState
                  state={state.issue.provider.options}
                  onRetry={() => onIntent({ type: 'origin.providers-retry-requested' })}
                />
                <Select.Root
                  open={nested === 'issue-provider'}
                  onOpenChange={(nextOpen) => {
                    if (state.issue.kind !== 'available') return;
                    if (state.issue.provider.availability.kind === 'unavailable') return;
                    onIntent({
                      type: 'overlay.changed',
                      overlay: {
                        kind: 'create-from',
                        nested: nextOpen ? 'issue-provider' : 'none',
                      },
                    });
                  }}
                  value={selectedOption(state.issue.provider.selection)?.id ?? undefined}
                  onValueChange={(providerId) => {
                    if (
                      providerId &&
                      state.issue.kind === 'available' &&
                      state.issue.provider.availability.kind === 'available'
                    ) {
                      onIntent({ type: 'origin.issue-provider-selected', providerId });
                    }
                  }}
                >
                  <Select.Trigger
                    className={styles.search}
                    aria-label="Issue provider"
                    aria-disabled={
                      state.issue.provider.availability.kind === 'unavailable' ? true : undefined
                    }
                    title={availabilityReason(state.issue.provider.availability)}
                    onClick={(event) => {
                      if (state.issue.kind !== 'available') return;
                      if (state.issue.provider.availability.kind === 'unavailable') {
                        event.preventDefault();
                      }
                    }}
                  >
                    <Select.Value placeholder="Issue provider" />
                  </Select.Trigger>
                  <Select.Content width="content-at-least-trigger">
                    {optionsFrom(state.issue.provider.options).map((provider) => (
                      <Select.Item
                        key={provider.id}
                        value={provider.id}
                        disabled={provider.availability.kind === 'unavailable'}
                      >
                        {provider.label}
                      </Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </>
            )}
            {state.activeKind === 'pull-request' && state.pullRequest.kind === 'available' && (
              <Tabs.Root
                value={state.pullRequest.status}
                onValueChange={(status) => {
                  if (status === 'open' || status === 'closed') {
                    onIntent({ type: 'origin.pull-request-status-changed', status });
                  }
                }}
              >
                <Tabs.List aria-label="Pull Request status">
                  <Tabs.Tab value="open">Open</Tabs.Tab>
                  <Tabs.Tab value="closed">Closed</Tabs.Tab>
                </Tabs.List>
              </Tabs.Root>
            )}
            {state.activeKind === 'branch' && state.branch.kind === 'available' && (
              <InlineOriginOptions
                label="Branches"
                query={state.branch.query}
                state={state.branch.options}
                selectedId={selectedId}
                getLabel={(branch) => branch.label}
                getDescription={(branch) => branch.description}
                onQueryChange={(query) =>
                  onIntent({ type: 'origin.query-changed', kind: 'branch', query })
                }
                onSelect={(id) =>
                  onIntent({ type: 'origin.selected', origin: { kind: 'branch', id } })
                }
                onRetry={() => onIntent({ type: 'origin.results-retry-requested', kind: 'branch' })}
              />
            )}
            {state.activeKind === 'issue' && state.issue.kind === 'available' && (
              <InlineOriginOptions
                label="Issues"
                query={state.issue.query}
                state={state.issue.options}
                selectedId={selectedId}
                getLabel={(issue) => `${issue.identifier} · ${issue.title}`}
                getDescription={(issue) => issue.stateLabel}
                onQueryChange={(query) =>
                  onIntent({ type: 'origin.query-changed', kind: 'issue', query })
                }
                onSelect={(id) =>
                  onIntent({ type: 'origin.selected', origin: { kind: 'issue', id } })
                }
                onRetry={() => onIntent({ type: 'origin.results-retry-requested', kind: 'issue' })}
              />
            )}
            {state.activeKind === 'pull-request' && state.pullRequest.kind === 'available' && (
              <InlineOriginOptions
                label="Pull Requests"
                query={state.pullRequest.query}
                state={state.pullRequest.options}
                selectedId={selectedId}
                getLabel={(pullRequest) => `#${pullRequest.number} · ${pullRequest.title}`}
                getDescription={(pullRequest) => pullRequest.headBranch}
                onQueryChange={(query) =>
                  onIntent({ type: 'origin.query-changed', kind: 'pull-request', query })
                }
                onSelect={(id) =>
                  onIntent({
                    type: 'origin.selected',
                    origin: { kind: 'pull-request', id },
                  })
                }
                onRetry={() =>
                  onIntent({
                    type: 'origin.results-retry-requested',
                    kind: 'pull-request',
                  })
                }
              />
            )}
            {state.activeKind === 'issue' && (
              <div className={styles.popupFooter}>
                <Button
                  size="sm"
                  onClick={() => onIntent({ type: 'origin.manage-integrations-requested' })}
                >
                  Manage integrations
                </Button>
              </div>
            )}
          </>
        )}
      </Popover.Content>
    </Popover.Root>
  );
}
