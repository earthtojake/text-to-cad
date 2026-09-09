const FIREFOX_VERSION = '140.0';

// Sites (notably Google sign-in) block embedded Chromium views by detecting the
// `Electron/x.y` and app-name tokens Chromium appends to the default user agent.
export function stripEmbeddedBrowserTokens(userAgent: string, appName: string): string {
  const escapedAppName = appName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return userAgent
    .replace(new RegExp(`\\s${escapedAppName}/\\S+`, 'i'), '')
    .replace(/\sElectron\/\S+/i, '')
    .trim();
}

// Google rejects OAuth/sign-in from embedded Chromium-based views even with the
// Electron token stripped ("This browser or app may not be secure"). Presenting
// as Firefox on Google's auth hosts is the established workaround used by
// Electron-based browsers (Wexond, Ferdium).
export function firefoxUserAgent(platform: NodeJS.Platform = process.platform): string {
  const os =
    platform === 'darwin'
      ? 'Macintosh; Intel Mac OS X 10.15'
      : platform === 'win32'
        ? 'Windows NT 10.0; Win64; x64'
        : 'X11; Linux x86_64';
  return `Mozilla/5.0 (${os}; rv:${FIREFOX_VERSION}) Gecko/20100101 Firefox/${FIREFOX_VERSION}`;
}

const GOOGLE_AUTH_HOSTS = new Set(['accounts.google.com', 'accounts.youtube.com']);

export function isGoogleAuthUrl(url: string): boolean {
  try {
    return GOOGLE_AUTH_HOSTS.has(new URL(url).hostname.toLowerCase());
  } catch {
    return false;
  }
}

export function userAgentForBrowserUrl(url: string, baseUserAgent: string): string {
  return isGoogleAuthUrl(url) ? firefoxUserAgent() : baseUserAgent;
}
