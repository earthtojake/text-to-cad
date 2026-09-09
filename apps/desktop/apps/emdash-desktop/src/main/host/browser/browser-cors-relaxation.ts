export type BrowserCorsRequestHeaders = Record<string, string>;
export type BrowserCorsResponseHeaders = Record<string, string[]>;

export type BrowserCorsRelaxationRequest = {
  origin: string;
  requestedMethod?: string;
  requestedHeaders?: string;
};

const DEFAULT_ALLOWED_METHODS = 'GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD';

export function localDevelopmentCorsRelaxationRequest(
  requestHeaders: BrowserCorsRequestHeaders
): BrowserCorsRelaxationRequest | null {
  const origin = headerValue(requestHeaders, 'origin');
  if (!origin || !isLocalDevelopmentOrigin(origin)) return null;

  return {
    origin,
    requestedMethod: headerValue(requestHeaders, 'access-control-request-method'),
    requestedHeaders: headerValue(requestHeaders, 'access-control-request-headers'),
  };
}

export function applyLocalDevelopmentCorsRelaxation(
  responseHeaders: BrowserCorsResponseHeaders,
  request: BrowserCorsRelaxationRequest
): BrowserCorsResponseHeaders {
  const next = { ...responseHeaders };
  setHeader(next, 'Access-Control-Allow-Origin', [request.origin]);
  setHeader(next, 'Access-Control-Allow-Credentials', ['true']);
  setHeader(next, 'Access-Control-Allow-Methods', [
    request.requestedMethod ?? DEFAULT_ALLOWED_METHODS,
  ]);
  if (request.requestedHeaders) {
    setHeader(next, 'Access-Control-Allow-Headers', [request.requestedHeaders]);
  }
  if (request.requestedMethod) {
    setHeader(next, 'Access-Control-Max-Age', ['86400']);
  }
  appendHeaderToken(next, 'Vary', 'Origin');
  return next;
}

function headerValue(headers: BrowserCorsRequestHeaders, name: string): string | undefined {
  const entry = Object.entries(headers).find(([key]) => key.toLowerCase() === name);
  return entry?.[1];
}

function setHeader(headers: BrowserCorsResponseHeaders, name: string, value: string[]): void {
  deleteHeader(headers, name);
  headers[name] = value;
}

function appendHeaderToken(headers: BrowserCorsResponseHeaders, name: string, token: string): void {
  const existing = Object.entries(headers).find(
    ([key]) => key.toLowerCase() === name.toLowerCase()
  );
  if (!existing) {
    headers[name] = [token];
    return;
  }

  const [existingName, values] = existing;
  const tokens = new Set(
    values
      .flatMap((value) => value.split(','))
      .map((value) => value.trim())
      .filter(Boolean)
  );
  tokens.add(token);
  headers[existingName] = [Array.from(tokens).join(', ')];
}

function deleteHeader(headers: BrowserCorsResponseHeaders, name: string): void {
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === name.toLowerCase()) delete headers[key];
  }
}

function isLocalDevelopmentOrigin(value: string): boolean {
  let origin: URL;
  try {
    origin = new URL(value);
  } catch {
    return false;
  }
  if (origin.protocol !== 'http:' && origin.protocol !== 'https:') return false;
  return isLocalDevelopmentHost(origin.hostname);
}

function isLocalDevelopmentHost(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return (
    host === 'localhost' || host.endsWith('.localhost') || host === '127.0.0.1' || host === '[::1]'
  );
}
