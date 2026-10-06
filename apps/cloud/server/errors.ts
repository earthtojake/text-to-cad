// One error type for everything a caller can be told: an HTTP status, a stable code and a
// message written for the person (or agent) who has to act on it.

export class CloudError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown> | undefined;
  /** Response headers the error carries (a 401's WWW-Authenticate). */
  headers: Record<string, string>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>, headers: Record<string, string> = {}) {
    super(message);
    this.name = 'CloudError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.headers = headers;
  }
}

export const badRequest = (message: string, details?: Record<string, unknown>) =>
  new CloudError(400, 'invalid_request', message, details);

export const notFound = (message: string) => new CloudError(404, 'not_found', message);

export const forbidden = (message: string) => new CloudError(403, 'forbidden', message);

export const unauthorized = (message = 'Sign in first: this needs an API key or an OAuth token.') =>
  new CloudError(401, 'unauthorized', message);

export function errorBody(error: CloudError) {
  return { error: { code: error.code, message: error.message, ...(error.details ?? {}) } };
}

export function isCloudError(error: unknown): error is CloudError {
  return error instanceof CloudError;
}
