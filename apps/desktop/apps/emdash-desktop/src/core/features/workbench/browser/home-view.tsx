import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { Button, DropdownMenu } from '@emdash/ui/react/primitives';
import { Box, Check, ChevronDown, Folder, FolderPlus, Send } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { motion } from 'motion/react';
import { Fragment, useEffect, useState } from 'react';
import {
  firstAvailableProjectId,
  getProjectSshConnectionId,
  getProjectManagerStore,
  projectDisplayName,
  projectViewKind,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { AddProjectMenu } from '@core/features/projects/contributions/browser/add-project-menu';
import { tasksBrowserContributions } from '@core/features/tasks/contributions/browser';
import { homeViewDef } from '@core/features/workbench/contributions/views';
import { useViewParams } from '@core/primitives/navigation/browser/navigation-hooks';
import { defineViewRuntime } from '@core/primitives/views/react';
import { NewChatAgentModelSelector } from './new-chat-agent-model-selector';

/**
 * A new chat remains an in-memory draft until the first message is sent. The
 * selected project is part of the composer, matching Codex's project flow and
 * avoiding empty tasks when someone only opens a folder to inspect it.
 */
export const HomeMainPanel = observer(function HomeMainPanel() {
  const params = useViewParams(homeViewDef);
  const projectManager = getProjectManagerStore();
  const projects = Array.from(projectManager.projects.entries())
    .filter(([, project]) => projectViewKind(project) === 'ready')
    .map(([id, project]) => ({ id, name: projectDisplayName(project) ?? 'Untitled project' }));
  const requestedProjectId = params?.projectId;
  const projectIds = projects.map(({ id }) => id).join('\n');
  const fallbackProjectId = projects[0]?.id;
  const initialProjectId =
    requestedProjectId && projects.some(({ id }) => id === requestedProjectId)
      ? requestedProjectId
      : firstAvailableProjectId();
  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>(initialProjectId);
  const [prompt, setPrompt] = useState('');
  const [modelSelection, setModelSelection] = useState<{
    providerId: AgentProviderId;
    modelId: string;
  } | null>(null);

  useEffect(() => {
    if (requestedProjectId && projectIds.split('\n').includes(requestedProjectId)) {
      setSelectedProjectId(requestedProjectId);
    }
  }, [projectIds, requestedProjectId]);

  useEffect(() => {
    if (!selectedProjectId || !projectIds.split('\n').includes(selectedProjectId)) {
      setSelectedProjectId(fallbackProjectId);
    }
  }, [fallbackProjectId, projectIds, selectedProjectId]);

  const selectedProject = projects.find(({ id }) => id === selectedProjectId);
  const newChat = tasksBrowserContributions.useStartBlankChat(selectedProjectId);
  const selectedModelId =
    modelSelection?.providerId === newChat.providerId ? modelSelection.modelId : null;
  const canSend = Boolean(selectedProjectId && prompt.trim() && !newChat.busy && !newChat.disabled);
  const projectItems = projects.map((project) => ({
    ...project,
    selected: project.id === selectedProjectId,
  }));

  const submit = async () => {
    if (!canSend || !selectedProjectId) return;
    const text = prompt.trim();
    setPrompt('');
    const result = await newChat.start(selectedProjectId, text, selectedModelId ?? undefined);
    if (!result) setPrompt(text);
  };

  return (
    <motion.main
      className="flex h-full flex-col overflow-y-auto bg-background text-foreground"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      <div className="mx-auto flex min-h-full w-full max-w-3xl flex-1 flex-col justify-center px-6 py-12">
        <div className="mb-7 text-center">
          <span className="mx-auto mb-4 flex size-10 items-center justify-center rounded-xl border border-border bg-background-1">
            <Box className="size-4" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight">What would you like to build?</h1>
          <p className="mt-2 text-sm text-foreground-muted">
            Start with a request. CAD and other outputs will open beside the chat.
          </p>
        </div>

        <form
          className="rounded-2xl border border-border bg-background-1 p-2 shadow-sm focus-within:ring-[3px] focus-within:ring-ring"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <textarea
            autoFocus
            value={prompt}
            rows={4}
            placeholder="Describe a part, assembly, drawing, or engineering task…"
            aria-label="New chat message"
            className="block min-h-28 w-full resize-none border-0 bg-transparent px-3 py-2 text-sm text-foreground outline-none placeholder:text-foreground-passive focus:ring-0"
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
              event.preventDefault();
              void submit();
            }}
          />
          <div className="flex items-center justify-between gap-2 px-1 pb-1">
            <div className="flex min-w-0 items-center gap-1">
              <DropdownMenu.Root>
                <DropdownMenu.Trigger
                  render={
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="max-w-64 min-w-0 justify-start gap-1.5 px-2"
                      aria-label="Choose project"
                      disabled={projects.length === 0}
                    >
                      <Folder className="size-3.5 shrink-0" />
                      <span className="truncate">{selectedProject?.name ?? 'Choose project'}</span>
                      <ChevronDown className="size-3.5 shrink-0 text-foreground-passive" />
                    </Button>
                  }
                />
                <DropdownMenu.Content align="start" width="content-at-least-trigger">
                  {projectItems.map((project) => (
                    <DropdownMenu.Item
                      key={project.id}
                      onClick={() => setSelectedProjectId(project.id)}
                    >
                      <Folder className="size-4" />
                      <span className="min-w-0 flex-1 truncate">{project.name}</span>
                      {project.selected ? <Check className="size-4" /> : null}
                    </DropdownMenu.Item>
                  ))}
                </DropdownMenu.Content>
              </DropdownMenu.Root>
              <AddProjectMenu
                align="start"
                trigger={
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    icon={projects.length > 0}
                    className={projects.length === 0 ? 'gap-1.5 px-2' : undefined}
                    aria-label="Add project"
                  >
                    <FolderPlus className="size-3.5" />
                    {projects.length === 0 ? <span>Add project</span> : null}
                  </Button>
                }
              />
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <NewChatAgentModelSelector
                providerId={newChat.providerId}
                modelId={selectedModelId}
                connectionId={
                  selectedProjectId ? getProjectSshConnectionId(selectedProjectId) : undefined
                }
                installedProviderIds={newChat.installedProviderIds}
                disabled={newChat.busy}
                onProviderChange={newChat.setProvider}
                onModelChange={(modelId) => {
                  setModelSelection(
                    modelId && newChat.providerId
                      ? { providerId: newChat.providerId, modelId }
                      : null
                  );
                }}
              />
              <Button
                type="submit"
                variant="primary"
                size="sm"
                icon
                disabled={!canSend}
                aria-label={newChat.busy ? 'Starting chat' : 'Send message'}
              >
                <Send className="size-3.5" />
              </Button>
            </div>
          </div>
        </form>
        {projects.length === 0 ? (
          <p className="mt-3 text-center text-xs text-foreground-muted">
            Add a project folder to give the chat files to work with.
          </p>
        ) : !newChat.providerId ? (
          <p className="mt-3 text-center text-xs text-foreground-muted">
            Choose or connect Claude or Codex before sending.
          </p>
        ) : null}
      </div>
    </motion.main>
  );
});

export const homeViewRuntime = defineViewRuntime(homeViewDef, {
  slots: {
    wrap: Fragment,
    main: HomeMainPanel,
  },
});
