import { createSkillModal } from '../browser/components/CreateSkillModal';
import { skillDetailModal } from '../browser/components/SkillDetailModal';

export const skillsBrowserContributions = {
  modalDefs: [createSkillModal, skillDetailModal],
} as const;
