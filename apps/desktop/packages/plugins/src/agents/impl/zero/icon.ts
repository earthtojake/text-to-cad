import type { PluginIconAsset } from '@emdash/shared/plugins';

export const icon: PluginIconAsset = {
  kind: 'svg',
  alt: 'Zero CLI',
  variants: [
    {
      minSize: 0,
      light: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#070708"/><text x="32" y="46" font-family="ui-monospace, Menlo, monospace" font-size="42" font-weight="800" text-anchor="middle" fill="#caff3f">0</text></svg>`,
    },
  ],
};
