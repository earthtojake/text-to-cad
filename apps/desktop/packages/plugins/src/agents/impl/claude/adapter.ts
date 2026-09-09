import { defineAdapterAsset } from '../../helpers/adapter-assets';

export const claudeAdapter = defineAdapterAsset({
  name: 'claude-acp',
  specifier: '@agentclientprotocol/claude-agent-acp/dist/index.js',
  format: 'esm',
});
