import { addRemoteModal } from '../browser/add-remote-modal';
import { taskModal } from '../browser/create-task-modal/create-task-modal';
import { deleteTaskModal } from '../browser/delete-task-modal';
import { renameTaskModal } from '../browser/rename-task-modal';
import { useStartBlankChat } from '../browser/start-blank-chat';
import { taskViewRuntime } from '../browser/view';

export const tasksBrowserContributions = {
  views: [taskViewRuntime],
  modalDefs: [taskModal, renameTaskModal, addRemoteModal, deleteTaskModal],
  useStartBlankChat,
} as const;
