/**
 * The git credential-helper wire protocol (`git credential fill` format):
 * newline-separated `key=value` lines, terminated by a blank line or EOF.
 * Values never contain newlines or NUL bytes.
 *
 * Used by the emdash git credential helper channel: git writes a request to
 * the helper's stdin, the helper forwards it verbatim to the desktop, and the
 * desktop answers with the same format (typically `username` + `password`).
 */

export type GitCredentialRequest = Record<string, string>;

export function parseGitCredentialRequest(text: string): GitCredentialRequest {
  const request: GitCredentialRequest = {};
  for (const rawLine of text.split('\n')) {
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
    // A blank line terminates the request.
    if (line === '') break;
    const separator = line.indexOf('=');
    if (separator <= 0) continue;
    request[line.slice(0, separator)] = line.slice(separator + 1);
  }
  return request;
}

export function serializeGitCredentialResponse(fields: Record<string, string>): string {
  let out = '';
  for (const [key, value] of Object.entries(fields)) {
    if (/[\n\r\0=]/.test(key) || key === '') {
      throw new Error('Invalid git credential response key');
    }
    if (/[\n\r\0]/.test(value)) {
      throw new Error('Invalid git credential response value');
    }
    out += `${key}=${value}\n`;
  }
  return out;
}
