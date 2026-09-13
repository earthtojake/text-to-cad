import type { SkillFrontmatter } from './types';

type BlockScalarStyle = 'literal' | 'folded';

export function isValidSkillName(name: string): boolean {
  return /^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]?$/.test(name) && !name.includes('--');
}

export function parseFrontmatter(content: string): {
  frontmatter: SkillFrontmatter;
  body: string;
} {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!match) {
    return {
      frontmatter: { name: '', description: '' },
      body: content,
    };
  }

  const yamlBlock = match[1];
  const body = match[2];
  const frontmatter: Record<string, string> = {};
  const lines = yamlBlock.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const colonIdx = line.indexOf(':');
    if (colonIdx === -1) continue;
    const key = line.slice(0, colonIdx).trim();
    let value = line.slice(colonIdx + 1).trim();
    const blockScalarStyle = getBlockScalarStyle(value);
    if (blockScalarStyle) {
      const { value: blockValue, nextIndex } = parseBlockScalar(lines, i, blockScalarStyle);
      value = blockValue;
      i = nextIndex;
    } else {
      value = unquoteYamlValue(value);
    }
    if (key) frontmatter[key] = value;
  }

  return {
    frontmatter: {
      name: frontmatter.name || '',
      description: frontmatter.description || '',
      license: frontmatter.license,
      compatibility: frontmatter.compatibility,
      'allowed-tools': frontmatter['allowed-tools'],
    },
    body,
  };
}

export function generateSkillMd(name: string, description: string, body?: string): string {
  const escapedName = escapeYamlDoubleQuoted(name);
  const escapedDesc = escapeYamlDoubleQuoted(description);
  const defaultBody = `# ${name}\n\n${description}\n`;
  const content = body && body.trim() ? body.trim() : defaultBody;
  return `---
name: "${escapedName}"
description: "${escapedDesc}"
---

${content}
`;
}

function getBlockScalarStyle(value: string): BlockScalarStyle | null {
  if (/^\|[+-]?$/.test(value)) return 'literal';
  if (/^>[+-]?$/.test(value)) return 'folded';
  return null;
}

function parseBlockScalar(
  lines: string[],
  headerIndex: number,
  style: BlockScalarStyle
): { value: string; nextIndex: number } {
  const headerIndent = countIndent(lines[headerIndex]);
  const blockLines: string[] = [];
  let nextIndex = headerIndex;

  for (let i = headerIndex + 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() && countIndent(line) <= headerIndent) break;
    blockLines.push(line);
    nextIndex = i;
  }

  const contentIndent = Math.min(
    ...blockLines.filter((line) => line.trim()).map((line) => countIndent(line))
  );
  const normalizedLines = blockLines.map((line) =>
    Number.isFinite(contentIndent) ? line.slice(contentIndent) : ''
  );

  if (style === 'folded') {
    return {
      value: normalizedLines.join(' ').replace(/\s+/g, ' ').trim(),
      nextIndex,
    };
  }
  return { value: normalizedLines.join('\n').trim(), nextIndex };
}

function countIndent(line: string): number {
  return line.match(/^\s*/)?.[0].length ?? 0;
}

function unquoteYamlValue(value: string): string {
  const wasDoubleQuoted = value.startsWith('"') && value.endsWith('"');
  const wasSingleQuoted = value.startsWith("'") && value.endsWith("'");
  if (wasDoubleQuoted) return value.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, '\\');
  if (wasSingleQuoted) return value.slice(1, -1).replace(/''/g, "'");
  return value;
}

function escapeYamlDoubleQuoted(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}
