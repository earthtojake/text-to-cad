import { agentSignInModal } from '../browser/agents-page/AgentSignInModal';
import { githubConnectModal } from '../browser/components/github-connect-modal';
import { githubDeviceFlowModal } from '../browser/github-device-flow-modal';
import { settingsViewRuntime } from '../browser/settings-view';

export const settingsBrowserContributions = {
  views: [settingsViewRuntime],
  modalDefs: [githubConnectModal, agentSignInModal, githubDeviceFlowModal],
} as const;
