import { addMachineModal } from '../browser/add-machine-modal';
import { linkConversationModal } from '../browser/components/link-conversation-modal';

export const machinesBrowserContributions = {
  modalDefs: [addMachineModal, linkConversationModal],
} as const;
