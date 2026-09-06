/** The title a chat is born with, before anything has been said in it. */
export const BLANK_CHAT_TITLE = 'New chat';

const MAX_TITLE_LENGTH = 48;

/**
 * A sidebar title taken from the first thing the user asked: the first
 * non-empty line, whitespace collapsed, cut at a word boundary. Agents that
 * later announce a session title through ACP still win, because that rename
 * arrives after this one.
 */
export function titleFromPrompt(text: string, maxLength = MAX_TITLE_LENGTH): string | null {
  const line = text
    .split(/\r?\n/)
    .map((candidate) => candidate.replace(/\s+/g, ' ').trim())
    .find((candidate) => candidate.length > 0);
  if (!line) return null;
  const cleaned = line.replace(/^[#>*\-\s]+/, '').trim();
  if (cleaned.length <= maxLength) return cleaned;
  const cut = cleaned.slice(0, maxLength + 1);
  const boundary = cut.lastIndexOf(' ');
  const head = (
    boundary > maxLength / 2 ? cut.slice(0, boundary) : cut.slice(0, maxLength)
  ).replace(/[\s,;:.!?]+$/, '');
  return `${head}…`;
}

/**
 * Whether a chat still carries its birth title ("New chat", or "New chat 3"
 * when siblings exist) or none at all, and may take one from the first prompt.
 */
export function hasBlankChatTitle(title: string | null | undefined): boolean {
  const trimmed = (title ?? '').trim();
  if (trimmed.length === 0) return true;
  return new RegExp(`^${BLANK_CHAT_TITLE}( \\d+)?$`, 'i').test(trimmed);
}
