import type { BrowserLoadError } from '@core/primitives/browser/api';

export interface BrowserLoadErrorPresentation {
  heading: string;
  detail: string;
}

const ERROR_CONSTANT_PATTERN = /^(?:net::)?(err_[a-z0-9_]+)$/i;

// Subset of Chromium net error codes we map to a tailored message. Electron
// usually hands us the constant directly in `description`, but older paths only
// provide the numeric code, so we resolve both.
const ERROR_CODE_CONSTANTS: Record<number, string> = {
  [-7]: 'ERR_TIMED_OUT',
  [-21]: 'ERR_NETWORK_CHANGED',
  [-100]: 'ERR_CONNECTION_CLOSED',
  [-101]: 'ERR_CONNECTION_RESET',
  [-102]: 'ERR_CONNECTION_REFUSED',
  [-104]: 'ERR_CONNECTION_FAILED',
  [-105]: 'ERR_NAME_NOT_RESOLVED',
  [-106]: 'ERR_INTERNET_DISCONNECTED',
  [-107]: 'ERR_SSL_PROTOCOL_ERROR',
  [-109]: 'ERR_ADDRESS_UNREACHABLE',
  [-118]: 'ERR_CONNECTION_TIMED_OUT',
  [-137]: 'ERR_NAME_RESOLUTION_FAILED',
  [-200]: 'ERR_CERT_COMMON_NAME_INVALID',
  [-201]: 'ERR_CERT_DATE_INVALID',
  [-202]: 'ERR_CERT_AUTHORITY_INVALID',
  [-300]: 'ERR_INVALID_URL',
  [-501]: 'ERR_INSECURE_RESPONSE',
};

const UNREACHABLE = "This site can't be reached";

export function browserLoadErrorConstant(error: BrowserLoadError): string | null {
  const match = error.description.trim().match(ERROR_CONSTANT_PATTERN);
  if (match) return match[1].toUpperCase();
  if (error.code !== undefined && error.code in ERROR_CODE_CONSTANTS) {
    return ERROR_CODE_CONSTANTS[error.code];
  }
  return null;
}

export function browserLoadErrorCode(error: BrowserLoadError): string | null {
  const constant = browserLoadErrorConstant(error);
  if (constant) return constant;
  if (error.code === undefined) return null;
  return `Error ${error.code}`;
}

export function describeBrowserLoadError(
  error: BrowserLoadError,
  url: string
): BrowserLoadErrorPresentation {
  const host = hostLabel(error.url ?? url);
  const constant = browserLoadErrorConstant(error);

  switch (constant) {
    case 'ERR_NAME_NOT_RESOLVED':
    case 'ERR_NAME_RESOLUTION_FAILED':
      return {
        heading: UNREACHABLE,
        detail: `${host}'s server IP address could not be found.`,
      };
    case 'ERR_CONNECTION_REFUSED':
      return {
        heading: UNREACHABLE,
        detail: `${host} refused to connect.`,
      };
    case 'ERR_TIMED_OUT':
    case 'ERR_CONNECTION_TIMED_OUT':
      return {
        heading: UNREACHABLE,
        detail: `${host} took too long to respond.`,
      };
    case 'ERR_CONNECTION_RESET':
    case 'ERR_CONNECTION_CLOSED':
    case 'ERR_CONNECTION_FAILED':
      return {
        heading: UNREACHABLE,
        detail: `The connection to ${host} was interrupted.`,
      };
    case 'ERR_ADDRESS_UNREACHABLE':
      return {
        heading: UNREACHABLE,
        detail: `${host} is unreachable.`,
      };
    case 'ERR_INTERNET_DISCONNECTED':
      return {
        heading: 'No internet',
        detail: 'You appear to be offline.',
      };
    case 'ERR_NETWORK_CHANGED':
      return {
        heading: UNREACHABLE,
        detail: 'Your network connection changed.',
      };
    case 'ERR_SSL_PROTOCOL_ERROR':
    case 'ERR_INSECURE_RESPONSE':
      return {
        heading: "This site can't provide a secure connection",
        detail: `${host} sent an invalid response.`,
      };
    case 'ERR_CERT_COMMON_NAME_INVALID':
    case 'ERR_CERT_DATE_INVALID':
    case 'ERR_CERT_AUTHORITY_INVALID':
      return {
        heading: 'Your connection is not private',
        detail: `${host}'s security certificate is not trusted.`,
      };
    case 'ERR_INVALID_URL':
      return {
        heading: UNREACHABLE,
        detail: "The web address isn't valid.",
      };
    default: {
      const description = error.description.trim();
      const isConstant = ERROR_CONSTANT_PATTERN.test(description);
      const detail =
        description.length > 0 && !isConstant
          ? sentence(description)
          : `${host} could not be loaded.`;
      return {
        heading: UNREACHABLE,
        detail,
      };
    }
  }
}

export function hostLabel(url: string): string {
  const trimmed = url.trim();
  if (trimmed.length === 0 || trimmed === 'about:blank') return 'This site';
  try {
    const parsed = new URL(trimmed);
    return parsed.hostname || trimmed;
  } catch {
    return trimmed;
  }
}

function sentence(value: string): string {
  const text = value.charAt(0).toUpperCase() + value.slice(1);
  return /[.!?]$/.test(text) ? text : `${text}.`;
}
