/**
 * String-based redaction: scans the serialized log line for secrets and PII.
 * Applied in the file transport as a defense-in-depth backstop for variadic
 * call sites that may embed secrets in message text or raw Error strings.
 *
 * Also exports DEFAULT_REDACT_PATHS for structural (field-path) redaction
 * via pino/fast-redact.
 */

type RedactionReplacement = string | ((substring: string, ...args: string[]) => string);

const SECRET_KEY_NAMES =
  'authorization|api[_-]?key|token|password|passphrase|secret|access[_-]?token|refresh[_-]?token|client[_-]?secret';

const SECRET_PATTERNS: Array<[RegExp, RedactionReplacement]> = [
  // JSON-quoted key/value: handles both "key":"value" and escaped \"key\":\"value\"
  [
    new RegExp(`(\\\\?")(${SECRET_KEY_NAMES})(\\\\?")(\\s*:\\s*)\\\\?"[^"\\\\]*\\\\?"`, 'gi'),
    (_match, openQuote: string, keyName: string, closeQuote: string, separator: string) =>
      `${openQuote}${keyName}${closeQuote}${separator}${openQuote}[REDACTED]${openQuote}`,
  ],
  // Unquoted: key=value or key: bearer value
  [
    new RegExp(`\\b(${SECRET_KEY_NAMES})(\\s*[:=]\\s*)(?:bearer\\s+)?[^\\s,"'}]+`, 'gi'),
    '$1$2[REDACTED]',
  ],
  // PEM blocks (private keys)
  [/-----BEGIN[^-\n]{1,40}-----[\s\S]+?-----END[^-\n]{1,40}-----/g, '[REDACTED_PEM_BLOCK]'],
  // Known token prefixes — order matters: vendor-specific before generic
  [/\bgh[opsu]_[A-Za-z0-9]{36,255}\b/g, '[REDACTED_GITHUB_TOKEN]'],
  [/\bglpat-[A-Za-z0-9_-]{20,}\b/g, '[REDACTED_GITLAB_TOKEN]'],
  [/\bnpm_[A-Za-z0-9]{36,}\b/g, '[REDACTED_NPM_TOKEN]'],
  [/\bAKIA[0-9A-Z]{16}\b/g, '[REDACTED_AWS_KEY]'],
  [/\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b/g, '[REDACTED_STRIPE_KEY]'],
  [/\bsk-ant-[A-Za-z0-9_-]{20,}\b/g, '[REDACTED_ANTHROPIC_KEY]'],
  [/\bsk-[A-Za-z0-9_-]{20,}\b/g, '[REDACTED_OPENAI_KEY]'],
  [/\bxox[baprs]-[A-Za-z0-9-]{20,}\b/g, '[REDACTED_SLACK_TOKEN]'],
  [/\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, '[REDACTED_JWT]'],
];

const PII_PATTERNS: Array<[RegExp, RedactionReplacement]> = [
  // Any scheme://user:pass@ — covers postgres, mongodb, redis, mysql, amqp, https…
  [/\b([a-z][a-z0-9+.-]*:\/\/)[^\s:/?#@]+:[^\s@/?#]+@/gi, '$1[REDACTED_CREDENTIALS]@'],
  [/\b(git|hg|svn)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b/g, '$1@[REDACTED_HOST]'],
  [/\b(?:[A-F0-9]{2}:){5}[A-F0-9]{2}\b/gi, '[REDACTED_MAC]'],
  [/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, '[REDACTED_EMAIL]'],
  [/\b(?:\d{1,3}\.){3}\d{1,3}\b/g, '[REDACTED_IP]'],
  [/\b(?:[A-F0-9]{1,4}:){2,7}[A-F0-9]{1,4}\b/gi, '[REDACTED_IP]'],
  [/\/Users\/[^\s/]+/gi, '/Users/[REDACTED_USER]'],
  [/\/home\/[^\s/]+/g, '/home/[REDACTED_USER]'],
  [/[A-Z]:\\Users\\[^\s\\]+/gi, (match) => `${match.slice(0, 9)}[REDACTED_USER]`],
];

function applyRedactions(value: string, patterns: Array<[RegExp, RedactionReplacement]>): string {
  return patterns.reduce(
    (redacted, [pattern, replacement]) => redacted.replace(pattern, replacement as string),
    value
  );
}

export function redactSecrets(value: string): string {
  return applyRedactions(value, SECRET_PATTERNS);
}

export function redactPii(value: string): string {
  return applyRedactions(value, PII_PATTERNS);
}

export function redactAll(value: string): string {
  return redactPii(redactSecrets(value));
}

/**
 * Field-path list for structural (pino/fast-redact) redaction.
 * Redacts well-known sensitive field names from structured log objects.
 * Used as the `redact` option in createPinoLogger.
 */
export const DEFAULT_REDACT_PATHS: string[] = [
  'token',
  'password',
  'secret',
  'passphrase',
  '*.token',
  '*.password',
  '*.secret',
  '*.passphrase',
  'authorization',
  'req.headers.authorization',
  'request.headers.authorization',
  '*.authorization',
  'set-cookie',
  'headers["set-cookie"]',
  'apiKey',
  'api_key',
  '*.apiKey',
  '*.api_key',
  'accessToken',
  'access_token',
  'refreshToken',
  'refresh_token',
  '*.accessToken',
  '*.access_token',
  '*.refreshToken',
  '*.refresh_token',
  'clientSecret',
  'client_secret',
  '*.clientSecret',
  '*.client_secret',
  'sessionToken',
  'session_token',
  '*.sessionToken',
  '*.session_token',
];
