const TRAILING_URL_CHARS_PATTERN = /[,.!?;:'"<>}\]]+$/;
const URL_CONTINUATION_CHARS_PATTERN = /[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]/;

export function normalizeExternalHttpUrl(value: string): string {
  let url = value.trim();
  url = joinMultilineUrl(url);
  url = trimTrailingText(url);
  url = url.replace(TRAILING_URL_CHARS_PATTERN, '');

  while (url.endsWith(')') && hasExtraClosingParen(url)) {
    url = url.slice(0, -1);
  }

  return url;
}

function hasExtraClosingParen(value: string): boolean {
  let balance = 0;

  for (const char of value) {
    if (char === '(') {
      balance += 1;
    } else if (char === ')') {
      balance -= 1;
    }
  }

  return balance < 0;
}

function joinMultilineUrl(value: string): string {
  return value.replace(/\r?\n[ \t]*/g, (lineBreak, offset) => {
    const previousChar = value[offset - 1];
    const nextChar = value[offset + lineBreak.length];
    if (!previousChar || !nextChar || !URL_CONTINUATION_CHARS_PATTERN.test(nextChar)) {
      return lineBreak;
    }

    const hasIndent = /[ \t]$/.test(lineBreak);
    const breaksUrlSegment = /[-._~:/?#[\]@!$&'()*+,;=%]/.test(previousChar);
    const startsIndentedLabel = /^[A-Za-z][A-Za-z0-9_-]*:/.test(
      value.slice(offset + lineBreak.length)
    );

    if (hasIndent && !breaksUrlSegment && startsIndentedLabel) {
      return lineBreak;
    }

    return hasIndent || breaksUrlSegment ? '' : lineBreak;
  });
}

function trimTrailingText(value: string): string {
  const trailingTextIndex = value.search(/[ \t\r\n]/);
  return trailingTextIndex === -1 ? value : value.slice(0, trailingTextIndex);
}
