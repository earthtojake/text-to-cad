const FENCE_RE = /([ \t]*)(`{3,}|~{3,})/y;
const TICKS_RE = /`+/y;

const isEscaped = (value: string, index: number) => {
  let backslashes = 0;
  for (let cursor = index - 1; cursor >= 0 && value[cursor] === '\\'; cursor -= 1) {
    backslashes += 1;
  }
  return backslashes % 2 === 1;
};

const findClosingDelimiter = (value: string, delimiter: string, start: number) => {
  for (let index = start; index < value.length; index += 1) {
    if (value.startsWith(delimiter, index) && !isEscaped(value, index)) {
      return index;
    }
  }
  return -1;
};

const appendDisplayMath = (result: string, value: string) => {
  const trimmedResult = result.trimEnd();
  const prefix = trimmedResult.length > 0 ? '\n' : '';
  return `${trimmedResult}${prefix}$$\n${value.trim()}\n$$\n`;
};

/**
 * remark-math only handles dollar delimiters; normalize LaTeX-style \(...\)
 * and \[...\] to $...$ and $$...$$ before parsing. Skips code spans and
 * fenced code blocks.
 */
export const normalizeLatexDelimiters = (content: string) => {
  let result = '';
  let index = 0;
  let inFence = false;
  let fenceMarker = '';

  while (index < content.length) {
    const atLineStart = index === 0 || content[index - 1] === '\n';

    if (atLineStart) {
      FENCE_RE.lastIndex = index;
      const fenceMatch = FENCE_RE.exec(content);
      if (fenceMatch) {
        const marker = fenceMatch[2]!;
        if (!inFence) {
          inFence = true;
          fenceMarker = marker;
        } else if (marker[0] === fenceMarker[0] && marker.length >= fenceMarker.length) {
          inFence = false;
          fenceMarker = '';
        }
      }
    }

    if (inFence) {
      result += content[index];
      index += 1;
      continue;
    }

    if (content[index] === '`') {
      TICKS_RE.lastIndex = index;
      const ticks = TICKS_RE.exec(content)![0];
      const closing = content.indexOf(ticks, index + ticks.length);
      if (closing !== -1) {
        result += content.slice(index, closing + ticks.length);
        index = closing + ticks.length;
        continue;
      }
    }

    if (content.startsWith('$$', index) && !isEscaped(content, index)) {
      const closing = findClosingDelimiter(content, '$$', index + 2);
      if (closing !== -1) {
        result = appendDisplayMath(result, content.slice(index + 2, closing));
        index = closing + 2;
        continue;
      }
    }

    const delimiter = content.startsWith('\\[', index)
      ? { open: '\\[', close: '\\]', display: true }
      : content.startsWith('\\(', index)
        ? { open: '\\(', close: '\\)', display: false }
        : null;

    if (delimiter) {
      const closing = findClosingDelimiter(content, delimiter.close, index + delimiter.open.length);
      if (closing !== -1) {
        const inner = content.slice(index + delimiter.open.length, closing).trim();
        result = delimiter.display ? appendDisplayMath(result, inner) : `${result}$${inner}$`;
        index = closing + delimiter.close.length;
        continue;
      }
    }

    result += content[index];
    index += 1;
  }

  return result;
};
