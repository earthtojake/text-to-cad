/**
 * Secret<T> — explicit, type-enforced secret redaction.
 *
 * A wrapped value whose plaintext can only be read via the deliberate `.expose()`
 * call. Every other serialization path (JSON, template literals, console.log,
 * Node.js inspect) emits "[REDACTED]" instead.
 *
 * Usage:
 *   const token = secret(rawToken, 'github-token');
 *   log.info('request', { token });          // logs token: "[REDACTED]"
 *   octokit = new Octokit({ auth: token.expose() }); // single disclosure
 */

const SECRET_TAG = Symbol.for('emdash.secret');

export const REDACTED = '[REDACTED]';

export class Secret<T> {
  readonly [SECRET_TAG] = true as const;
  readonly #value: T;
  readonly #label: string;

  constructor(value: T, label = 'secret') {
    this.#value = value;
    this.#label = label;
  }

  /** The only way to read the underlying value. Intentionally verbose and greppable. */
  expose(): T {
    return this.#value;
  }

  /** Transform the secret without exposing the underlying value. */
  map<U>(fn: (value: T) => U): Secret<U> {
    return new Secret(fn(this.#value), this.#label);
  }

  get label(): string {
    return this.#label;
  }

  toString(): string {
    return REDACTED;
  }

  toJSON(): string {
    return REDACTED;
  }

  [Symbol.for('nodejs.util.inspect.custom')](): string {
    return `Secret<${this.#label}>(${REDACTED})`;
  }
}

/** Wrap a value as a Secret. */
export function secret<T>(value: T, label?: string): Secret<T> {
  return new Secret(value, label);
}

/** Type guard: true if value is a Secret instance (works across module copies). */
export function isSecret(value: unknown): value is Secret<unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as Record<symbol, unknown>)[SECRET_TAG] === true
  );
}

/**
 * Unwrap a Secret or pass a plain value through unchanged.
 * Useful at boundaries that accept either form.
 */
export function reveal<T>(value: Secret<T> | T): T {
  return isSecret(value) ? (value.expose() as T) : value;
}
