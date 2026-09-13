import type { ChatCommands } from '@core/features/conversations/api/browser/chat/chat-transcript';
// TODO(conversations-extraction): Inject task editor/file-opening behavior into ACP chat.
import { openFileInAdjacentPane } from '@core/features/editor/api/browser/open-file-in-file-editor';

const EXPLICIT_SCHEME_RE = /^[A-Za-z][A-Za-z\d+.-]*:/u;
const EDITOR_LOCATION_SUFFIX_RE = /(?::\d+(?::\d+)?|#L\d+(?:C\d+)?)$/u;
const BASENAME_WITH_LINE_SUFFIX_RE = /^[^/\\:]+\.[^/\\:]+:\d+(?::\d+)?$/u;
const WINDOWS_ABSOLUTE_PATH_RE = /^[A-Za-z]:[\\/]/u;
const WINDOWS_UNC_PATH_RE = /^\\\\[^\\]+\\[^\\]+/u;

type TranscriptLinkClassification = ReturnType<NonNullable<ChatCommands['classifyLink']>>;

type TranscriptFileContext = {
  projectId: string;
  taskId: string;
};

type TranscriptFileOpener = (projectId: string, taskId: string, filePath: string) => Promise<void>;

export type TranscriptFileCommands = {
  classifyLink: NonNullable<ChatCommands['classifyLink']>;
  onOpenFile: NonNullable<ChatCommands['onOpenFile']>;
  openMentionFile: (filePath: string) => void;
};

/**
 * Classifies markdown links at the Emdash host boundary. A scheme-less href is
 * a file path in a desktop agent transcript; explicit URI schemes, anchors,
 * query-only links, and protocol-relative URLs keep browser behavior. Editor
 * location suffixes are removed because the file opener accepts paths, not
 * line/column annotations.
 */
export function classifyTranscriptLink(href: string): TranscriptLinkClassification {
  const target = href.trim();
  if (!target || target.startsWith('#') || target.startsWith('?') || target.startsWith('//')) {
    return { kind: 'external' };
  }
  const viewerFile = cadViewerFileFromUrl(target);
  if (viewerFile) return { kind: 'workspace-file', path: viewerFile };
  const filePath = target.replace(EDITOR_LOCATION_SUFFIX_RE, '');
  if (
    target.startsWith('/') ||
    WINDOWS_ABSOLUTE_PATH_RE.test(target) ||
    WINDOWS_UNC_PATH_RE.test(target) ||
    BASENAME_WITH_LINE_SUFFIX_RE.test(target)
  ) {
    return { kind: 'workspace-file', path: filePath };
  }
  if (EXPLICIT_SCHEME_RE.test(target)) return { kind: 'external' };
  return { kind: 'workspace-file', path: filePath };
}

/** All file affordances originating in chat preserve the transcript and open to its right. */
export function createTranscriptFileCommands(
  context: TranscriptFileContext,
  openFile: TranscriptFileOpener = openFileInAdjacentPane
): TranscriptFileCommands {
  const open = (filePath: string) => {
    void openFile(context.projectId, context.taskId, filePath);
  };

  return {
    classifyLink: classifyTranscriptLink,
    onOpenFile: ({ path }) => open(path),
    openMentionFile: open,
  };
}

const CAD_VIEWER_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

/**
 * The workspace file behind a CAD Viewer link. Agents that run the cad-viewer
 * skill post `http://127.0.0.1:<port>/?file=models/part.step`; Hardcore has its
 * own viewer beside the chat, so the link opens the file there instead of a
 * browser tab on a server that may already be gone.
 */
export function cadViewerFileFromUrl(href: string): string | null {
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
  if (!CAD_VIEWER_HOSTS.has(url.hostname)) return null;
  const file = url.searchParams.get('file')?.trim();
  if (!file) return null;
  const relative = file.replace(/^\/+/, '');
  return relative.length > 0 ? relative : null;
}
