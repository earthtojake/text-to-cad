import { EmptyState } from '@emdash/ui/react/components';
import { Button, Combobox, Dialog, ModalLayout } from '@emdash/ui/react/primitives';
import { useQuery } from '@tanstack/react-query';
import { ChevronsUpDown } from 'lucide-react';
import { useState } from 'react';
import { getMachinesClient } from '@core/features/machines/api/browser/client';
import { getProjectsWireClient } from '@core/features/projects/api/browser/client';
import { getTasksWireClient } from '@core/features/tasks/api/browser/client';
import { useModalController } from '@core/manifests/browser/modal-api';
import { defineModal } from '@core/primitives/modals/react';

export interface LinkConversationModalProps {
  /** SSH connection id of the conversation's host; null for the local machine. */
  connectionId: string | null;
  conversationTitle: string;
}

export interface LinkConversationModalResult {
  projectId: string;
  taskId: string;
}

type PickerOption = { id: string; name: string };

/** Projects on the conversation's host: linking across hosts would create a dead link. */
function useHostProjects(connectionId: string | null) {
  return useQuery({
    queryKey: ['linkConversationProjects', connectionId ?? 'local'],
    queryFn: async (): Promise<PickerOption[]> => {
      if (connectionId !== null) {
        const usage = await (await getMachinesClient()).getMachineUsage(undefined);
        return (usage[connectionId] ?? []).map((project) => ({
          id: project.id,
          name: project.name,
        }));
      }
      const projectsClient = await getProjectsWireClient();
      const projectList = await projectsClient.projectList.state(undefined, 'list').snapshot();
      return projectList.data.projects
        .filter((project) => project.type === 'local')
        .map((project) => ({ id: project.id, name: project.name }));
    },
    refetchOnWindowFocus: false,
  });
}

function useProjectTasks(projectId: string | null) {
  return useQuery({
    queryKey: ['linkConversationTasks', projectId],
    queryFn: async (): Promise<PickerOption[]> => {
      const client = await getTasksWireClient();
      const list = await client.taskList.state({ projectId: projectId! }, 'list').snapshot();
      return list.data.tasks.map((task) => ({ id: task.id, name: task.name }));
    },
    enabled: projectId !== null,
    refetchOnWindowFocus: false,
  });
}

function OptionCombobox({
  options,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  options: PickerOption[];
  value: PickerOption | null;
  onChange: (option: PickerOption | null) => void;
  placeholder: string;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState('');
  const filtered = query
    ? options.filter((option) => option.name.toLowerCase().includes(query.toLowerCase()))
    : options;

  return (
    <Combobox.Root
      value={value}
      onValueChange={onChange}
      onOpenChange={(open) => {
        if (!open) setQuery('');
      }}
      isItemEqualToValue={(a: PickerOption, b: PickerOption) => a.id === b.id}
      disabled={disabled}
    >
      <Combobox.Trigger className="data-popup-open:border-ring flex w-full items-center justify-between gap-2 rounded-lg border border-border px-2.5 py-2 text-sm transition-colors outline-none hover:bg-background-2 disabled:opacity-50">
        {value ? (
          <span className="truncate">{value.name}</span>
        ) : (
          <span className="text-foreground-muted">{placeholder}</span>
        )}
        <ChevronsUpDown className="size-4 shrink-0 text-foreground-passive" />
      </Combobox.Trigger>
      <Combobox.Content>
        <Combobox.Input
          value={query}
          onChange={(event) => setQuery((event.target as HTMLInputElement).value)}
          placeholder="Search…"
          showTrigger={false}
        />
        <Combobox.List className="max-h-52 overflow-y-auto p-1!">
          {filtered.map((option) => (
            <Combobox.Item key={option.id} value={option} showCheck={false} className="py-2 pr-3">
              <span className="truncate text-sm">{option.name}</span>
            </Combobox.Item>
          ))}
          {filtered.length === 0 && (
            <EmptyState label="No matches" className="border-none bg-transparent" />
          )}
        </Combobox.List>
      </Combobox.Content>
    </Combobox.Root>
  );
}

export function LinkConversationModal({
  connectionId,
  conversationTitle,
}: LinkConversationModalProps) {
  const modal = useModalController('linkConversationModal');
  const [project, setProject] = useState<PickerOption | null>(null);
  const [task, setTask] = useState<PickerOption | null>(null);
  const projects = useHostProjects(connectionId);
  const tasks = useProjectTasks(project?.id ?? null);

  return (
    <ModalLayout
      header={
        <Dialog.Header showCloseButton>
          <Dialog.Title>Link conversation to a task</Dialog.Title>
        </Dialog.Header>
      }
      footer={
        <Dialog.Footer>
          <Button type="button" variant="secondary" onClick={modal.dismiss}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="button"
            disabled={!project || !task}
            onClick={() => {
              if (project && task) {
                modal.complete({ projectId: project.id, taskId: task.id });
              }
            }}
          >
            Link
          </Button>
        </Dialog.Footer>
      }
    >
      <Dialog.Body className="flex flex-col gap-4">
        <p className="text-sm text-foreground-muted">
          Choose the task that <span className="text-foreground">“{conversationTitle}”</span> should
          appear under. Linking only annotates this device's registry; the conversation itself stays
          on its machine.
        </p>
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-foreground-muted">Project</span>
          <OptionCombobox
            options={projects.data ?? []}
            value={project}
            onChange={(next) => {
              setProject(next);
              setTask(null);
            }}
            placeholder={projects.isLoading ? 'Loading projects…' : 'Select a project…'}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-foreground-muted">Task</span>
          <OptionCombobox
            options={tasks.data ?? []}
            value={task}
            onChange={setTask}
            placeholder={
              !project
                ? 'Select a project first'
                : tasks.isLoading
                  ? 'Loading tasks…'
                  : 'Select a task…'
            }
            disabled={!project}
          />
        </div>
      </Dialog.Body>
    </ModalLayout>
  );
}

export const linkConversationModal = defineModal<LinkConversationModalResult>()({
  id: 'linkConversationModal',
  component: LinkConversationModal,
});
