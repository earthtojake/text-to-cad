import type { LinkedIssue } from '@core/primitives/linked-issues/api';

type IssueProviderType = LinkedIssue['provider'];

const ISSUE_TARGET_RE = /\((issue:[^\s)]+)\)/g;

export type IssueMentionTarget = {
  token: string;
  provider: IssueProviderType;
  identifier: string;
};

export type LoadIssueContext = (target: IssueMentionTarget) => Promise<LinkedIssue | null>;

export function issueMentionToken(provider: IssueProviderType, identifier: string): string {
  return `issue:${provider}:${identifier}`;
}

export function parseIssueMentionToken(token: string): IssueMentionTarget | null {
  if (!token.startsWith('issue:')) return null;
  const rest = token.slice('issue:'.length);
  const providerEnd = rest.indexOf(':');
  if (providerEnd <= 0) return null;
  const provider = rest.slice(0, providerEnd) as IssueProviderType;
  const identifier = rest.slice(providerEnd + 1);
  if (!identifier) return null;
  return { token, provider, identifier };
}

export function extractIssueMentionTargets(text: string): IssueMentionTarget[] {
  const seen = new Set<string>();
  const targets: IssueMentionTarget[] = [];
  let match: RegExpExecArray | null;

  while ((match = ISSUE_TARGET_RE.exec(text)) !== null) {
    const token = match[1];
    const target = token ? parseIssueMentionToken(token) : null;
    if (!target || seen.has(target.token)) continue;
    seen.add(target.token);
    targets.push(target);
  }

  return targets;
}

export function formatIssueProviderId(id: string): string {
  return id
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function buildIssueContextText(issue: LinkedIssue): string {
  const normalize = (s: string) => s.replace(/[\r\n]+/g, ' ').trim();

  const parts: string[] = [
    `Provider: ${formatIssueProviderId(issue.provider)}`,
    `Identifier: ${issue.identifier}`,
    `Title: ${issue.title}`,
    `URL: ${issue.url}`,
  ];

  if (issue.description) parts.push(`Description: ${normalize(issue.description)}`);
  if (issue.status) parts.push(`Status: ${issue.status}`);
  if (issue.assignees?.length) parts.push(`Assignees: ${issue.assignees.join(', ')}`);
  if (issue.project) parts.push(`Project: ${issue.project}`);

  let text = parts.join('. ');

  if (issue.context) {
    text += `\nContext:\n${issue.context}`;
  }

  return text;
}

export function buildIssueMentionContextBlock(
  target: IssueMentionTarget,
  issue: LinkedIssue
): string {
  return [
    `<issue_context provider="${escapeXmlAttr(target.provider)}" identifier="${escapeXmlAttr(
      target.identifier
    )}">`,
    buildIssueContextText(issue),
    '</issue_context>',
  ].join('\n');
}

export async function buildIssueMentionHiddenContext(
  text: string,
  loadIssue: LoadIssueContext
): Promise<string | undefined> {
  const targets = extractIssueMentionTargets(text);
  if (targets.length === 0) return undefined;

  const blocks = await Promise.all(
    targets.map(async (target) => {
      const issue = await loadIssue(target).catch(() => null);
      if (!issue) return null;
      return buildIssueMentionContextBlock(target, issue);
    })
  );

  const hiddenContext = blocks.filter((block): block is string => block !== null).join('\n\n');
  return hiddenContext.length > 0 ? hiddenContext : undefined;
}

function escapeXmlAttr(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
