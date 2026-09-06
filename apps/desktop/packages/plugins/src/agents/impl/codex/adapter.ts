import { defineAdapterAsset } from '../../helpers/adapter-assets';

export const codexAdapter = defineAdapterAsset({
  name: 'codex-acp',
  specifier: '@agentclientprotocol/codex-acp/dist/index.js',
  format: 'cjs',
  external: ['@openai/codex'],
});
