import { browserTaskTabContributions } from '@core/features/browser/contributions/tabs';
import { cadTaskTabContributions } from '@core/features/cad/contributions/tabs';
import { conversationTaskTabContributions } from '@core/features/conversations/contributions/tabs';
import { editorTaskTabContributions } from '@core/features/editor/contributions/tabs';
import { sourceControlTaskTabContributions } from '@core/features/source-control/contributions/tabs';
import { terminalTaskTabContributions } from '@core/features/terminals/contributions/tabs';

export const taskTabContributions = [
  ...conversationTaskTabContributions,
  ...editorTaskTabContributions,
  ...sourceControlTaskTabContributions,
  ...terminalTaskTabContributions,
  ...cadTaskTabContributions,
  ...browserTaskTabContributions,
] as const;
