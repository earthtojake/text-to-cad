export type LineCommentLike = {
  filePath: string;
  target?: DraftCommentTarget;
  targetKey?: string;
  lineNumber: number;
  content: string;
};

export type DraftCommentTarget =
  | { kind: 'working-tree'; group: 'disk' | 'staged'; path: string }
  | { kind: 'pr'; prNumber: number; baseOid: string; headOid: string; path: string }
  | { kind: 'commit'; originalSha: string | null; modifiedSha: string; path: string };

type FormatOptions = {
  includeIntro?: boolean;
  leadingNewline?: boolean;
};

export function getDraftCommentTargetPath(target: DraftCommentTarget): string {
  return target.path;
}

export function getDraftCommentTargetKey(target: DraftCommentTarget): string {
  switch (target.kind) {
    case 'working-tree':
      return JSON.stringify(['working-tree', target.group, target.path]);
    case 'pr':
      return JSON.stringify(['pr', target.prNumber, target.baseOid, target.headOid, target.path]);
    case 'commit':
      return JSON.stringify(['commit', target.originalSha, target.modifiedSha, target.path]);
  }
}

function escapeXmlText(value: string): string {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

function escapeXmlAttribute(value: string | number): string {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

const COMMENT_LINE = (c: LineCommentLike) => {
  return `    <comment line="${escapeXmlAttribute(c.lineNumber)}">${escapeXmlText(c.content)}</comment>`;
};

function targetAttributes(target: DraftCommentTarget): string {
  switch (target.kind) {
    case 'working-tree':
      return `kind="working-tree" group="${escapeXmlAttribute(target.group)}" path="${escapeXmlAttribute(target.path)}"`;
    case 'pr':
      return `kind="pr" prNumber="${escapeXmlAttribute(target.prNumber)}" baseOid="${escapeXmlAttribute(target.baseOid)}" headOid="${escapeXmlAttribute(target.headOid)}" path="${escapeXmlAttribute(target.path)}"`;
    case 'commit':
      return `kind="commit" originalSha="${escapeXmlAttribute(target.originalSha ?? 'root')}" modifiedSha="${escapeXmlAttribute(target.modifiedSha)}" path="${escapeXmlAttribute(target.path)}"`;
  }
}

const TARGET_BLOCK = (target: DraftCommentTarget, comments: LineCommentLike[]) =>
  `  <target ${targetAttributes(target)}>
${comments
  .sort((a, b) => a.lineNumber - b.lineNumber)
  .map(COMMENT_LINE)
  .join('\n')}
  </target>`;

const FILE_BLOCK = (filePath: string, comments: LineCommentLike[]) =>
  `  <target kind="file" path="${escapeXmlAttribute(filePath)}">
${comments
  .sort((a, b) => a.lineNumber - b.lineNumber)
  .map(COMMENT_LINE)
  .join('\n')}
  </target>`;

const COMMENTS_WRAPPER = (
  fileBlocks: string[]
) => `The user has left the following comments on the code changes:

<user_comments>
${fileBlocks.join('\n')}
</user_comments>`;

function groupByTarget(comments: LineCommentLike[]): Map<string, LineCommentLike[]> {
  const groups = new Map<string, LineCommentLike[]>();
  for (const c of comments) {
    const key = c.targetKey ?? (c.target ? getDraftCommentTargetKey(c.target) : c.filePath);
    const existing = groups.get(key) ?? [];
    existing.push(c);
    groups.set(key, existing);
  }
  return groups;
}

export function formatCommentsForAgent(
  comments: LineCommentLike[],
  { includeIntro = false, leadingNewline = false }: FormatOptions = {}
): string {
  if (!comments.length) return '';

  const byTarget = groupByTarget(comments);
  const fileBlocks = Array.from(byTarget.values()).map((targetComments) => {
    const target = targetComments[0]?.target;
    if (target) return TARGET_BLOCK(target, targetComments);
    return FILE_BLOCK(targetComments[0]?.filePath ?? '', targetComments);
  });
  const prefix = leadingNewline ? '\n' : '';

  if (includeIntro) {
    return `${prefix}${COMMENTS_WRAPPER(fileBlocks)}`;
  }

  return `${prefix}<user_comments>\n${fileBlocks.join('\n')}\n</user_comments>`;
}
