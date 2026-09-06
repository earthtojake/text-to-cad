import { ChevronDown, Laptop, Server } from 'lucide-react';
import type { RefObject } from 'react';
import { Button } from '../../primitives/button';
import type { CreateTaskModalProps } from './create-task-modal.types';
import { SearchableChoicePicker } from './searchable-choice-picker';
import * as styles from './create-task-modal.css';

export function ProjectPicker({
  state,
  open,
  triggerRef,
  onIntent,
}: {
  state: CreateTaskModalProps['state']['project'];
  open: boolean;
  triggerRef: RefObject<HTMLButtonElement | null>;
  onIntent: CreateTaskModalProps['onIntent'];
}) {
  return (
    <SearchableChoicePicker
      label="Project"
      query={state.query}
      selection={state.selection}
      options={state.options}
      open={open}
      triggerRef={triggerRef}
      triggerClassName={styles.selector}
      getLabel={(project) => project.label}
      getDescription={(project) =>
        project.location.kind === 'ssh'
          ? `${project.location.hostLabel} · ${project.path}`
          : project.path
      }
      renderTrigger={(selected) => (
        <>
          {selected?.location.kind === 'ssh' ? <Server /> : <Laptop />}
          <span className={styles.selectorText}>{selected?.label ?? 'Select a Project'}</span>
          <ChevronDown />
        </>
      )}
      renderFooter={() => (
        <Button size="sm" onClick={() => onIntent({ type: 'project.add-requested' })}>
          Add Project
        </Button>
      )}
      onOpenChange={(nextOpen) =>
        onIntent({
          type: 'overlay.changed',
          overlay: nextOpen ? { kind: 'project' } : { kind: 'none' },
        })
      }
      onQueryChange={(query) => onIntent({ type: 'project.query-changed', query })}
      onSelect={(projectId) => onIntent({ type: 'project.selected', projectId })}
      onRetry={() => onIntent({ type: 'project.retry-requested' })}
    />
  );
}
