import React from 'react';
import mcpDefaultSvg from '@/assets/images/mcp/mcp_default.svg?raw';
import { coerceRawSvgContent, prepareInlineSvgMarkup } from './mcp-icon-data';

const svgs = import.meta.glob('../../assets/images/mcp/*.svg', { query: '?raw', eager: true });

const FALLBACK_ICON_KEY = 'mcp_default';

const ICON_ALIASES: Record<string, string> = {
  amazonaws: 'aws_marketplace',
  aws: 'aws_marketplace',
  chrome: 'chrome_devtools',
  chrome_devtools_mcp: 'chrome_devtools',
  chrome_devtools_mcp_server: 'chrome_devtools',
  context_7: 'context7',
  dev_manager_mcp: 'dev_manager',
  dev_server_manager: 'dev_manager',
  duckdb: 'motherduck',
  exa_search: 'exa',
  googlebigquery: 'bigquery',
  googlechrome: 'chrome_devtools',
  graphql: 'graphos',
  huggingface: 'hugging_face',
  magicpatterns: 'magic_patterns',
  magic_patterns_mcp: 'magic_patterns',
  mcp_server_context7: 'context7',
  mcp_server_time: FALLBACK_ICON_KEY,
  microsoft: 'microsoft_learn',
  microsoftazure: 'azure',
  model_context_protocol: FALLBACK_ICON_KEY,
  parallel_search: 'parallel',
  shopify_dev: 'shopify',
};

function keyFromPath(path: string): string {
  return path
    .split('/')
    .pop()!
    .replace(/\.\w+$/, '');
}

const svgByKey = new Map(
  Object.entries(svgs)
    .map(([p, d]) => [keyFromPath(p), coerceRawSvgContent(d)])
    .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
);

const fallbackSvg = coerceRawSvgContent(mcpDefaultSvg) ?? svgByKey.get(FALLBACK_ICON_KEY) ?? '';

function normalizeIconKey(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\.com\b/g, '')
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

export function resolveMcpIconKey(iconKey?: string, name?: string): string | undefined {
  for (const candidate of [iconKey, name]) {
    if (!candidate) continue;

    const normalized = normalizeIconKey(candidate);
    const withoutMcpAffixes = normalized
      .replace(/^mcp_server_/, '')
      .replace(/^mcp_/, '')
      .replace(/_mcp$/, '')
      .replace(/_server$/, '');
    const candidates = [
      candidate,
      normalized,
      withoutMcpAffixes,
      ICON_ALIASES[normalized],
      ICON_ALIASES[withoutMcpAffixes],
    ].filter((key): key is string => !!key);

    for (const key of candidates) {
      if (key === FALLBACK_ICON_KEY || svgByKey.has(key)) {
        return key;
      }
    }
  }

  return undefined;
}

function getIcon(key: string): string | undefined {
  if (key === FALLBACK_ICON_KEY) {
    return fallbackSvg || undefined;
  }

  return svgByKey.get(key);
}

function renderSvgMarkup(svgContent: string): React.ReactNode {
  const processed = prepareInlineSvgMarkup(svgContent);
  return <div className="size-5" dangerouslySetInnerHTML={{ __html: processed }} />;
}

export const McpServerIcon: React.FC<{ name: string; iconKey?: string }> = ({ name, iconKey }) => {
  const resolvedIconKey = resolveMcpIconKey(iconKey, name);
  const icon = resolvedIconKey ? getIcon(resolvedIconKey) : undefined;
  const svgContent = icon ?? fallbackSvg;

  return (
    <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-background-2 transition-colors group-hover:bg-background-3">
      {svgContent ? renderSvgMarkup(svgContent) : null}
    </div>
  );
};
