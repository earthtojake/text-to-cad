import { createContext, useCallback, useContext, type ReactNode } from 'react';

export type OpenExternalLink = (href: string) => void;

const OpenExternalLinkContext = createContext<OpenExternalLink | undefined>(undefined);

export function ExternalLinkProvider({
  children,
  openExternalLink,
}: {
  readonly children: ReactNode;
  readonly openExternalLink: OpenExternalLink;
}) {
  return (
    <OpenExternalLinkContext.Provider value={openExternalLink}>
      {children}
    </OpenExternalLinkContext.Provider>
  );
}

export function useOpenExternalLink(): OpenExternalLink | undefined {
  return useContext(OpenExternalLinkContext);
}

/**
 * Builds an `onOpenLink` handler for the @emdash/ui Markdown component: tries
 * the optional custom handler first (e.g. workspace-relative links), then
 * claims http(s) links and routes them through the app's open-external flow.
 */
export function useMarkdownLinkOpener(
  custom?: (href: string) => boolean | void
): (href: string) => boolean {
  const openExternalLink = useOpenExternalLink();
  return useCallback(
    (href: string) => {
      if (custom?.(href)) return true;
      if (/^https?:\/\//i.test(href)) {
        openExternalLink?.(href);
        return true;
      }
      return false;
    },
    [custom, openExternalLink]
  );
}
