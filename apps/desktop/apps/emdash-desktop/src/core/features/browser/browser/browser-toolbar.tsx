import { Button, DropdownMenu, Input, Tooltip } from '@emdash/ui/react/primitives';
import {
  ArrowLeft,
  ArrowRight,
  Ellipsis,
  Focus,
  Globe,
  Loader2,
  Minus,
  Plus,
  RefreshCw,
  RotateCcw,
  Square,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import { getBrowserClient } from '@core/features/browser/api/browser/client';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { settingsViewDef } from '@core/features/settings/contributions/views';
import {
  BROWSER_DEFAULT_URL,
  BROWSER_DEFAULT_ZOOM_FACTOR,
  BROWSER_ISOLATED_PROFILE_ID,
  DEFAULT_BROWSER_PROFILES,
  browserProfileLabel,
  canZoomIn,
  canZoomOut,
  formatBrowserZoomPercent,
  isDefaultBrowserZoomFactor,
  nextBrowserZoomFactor,
  normalizeBrowserUrl,
  previousBrowserZoomFactor,
  type BrowserSessionSnapshot,
} from '@core/primitives/browser/api';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';
import { cn } from '@core/primitives/styling/browser/cn';
import {
  canOpenBrowserUrlExternally,
  captureBrowserScreenshot,
  clearBrowserData,
  confirmClearBrowserStorage,
  openBrowserUrlExternally,
} from './browser-toolbar-actions';
import { browserUrlInputText } from './browser-url-input';
import type { BrowserWebviewAdapter } from './browser-webview-types';

// Selection is conveyed by the checkmark alone (matching SelectItem); the base
// radio item pins a background on the checked row and mutes unchecked rows.
const PROFILE_RADIO_ITEM_CLASS = 'text-foreground data-checked:bg-transparent';

export function BrowserToolbar({
  session,
  adapter,
  autoFocusUrl,
  onNavigate,
  onGoBack,
  onGoForward,
  onReload,
  onForceReload,
  onSetZoomFactor,
  onFocusUrl,
}: {
  session: BrowserSessionSnapshot;
  adapter: BrowserWebviewAdapter | null;
  autoFocusUrl?: boolean;
  onNavigate?: (url: string) => boolean;
  onGoBack?: () => void;
  onGoForward?: () => void;
  onReload?: () => void;
  onForceReload?: () => void;
  onSetZoomFactor?: (factor: number) => void;
  onFocusUrl?: (focus: () => void) => void;
}) {
  const [urlText, setUrlText] = useState(browserUrlInputText(session.currentUrl));
  const [urlError, setUrlError] = useState<string | null>(null);
  const [failedFaviconUrl, setFailedFaviconUrl] = useState<string | null>(null);
  const [screenshotSpin, triggerScreenshotSpin] = useTransientFlag(300);
  const urlInputRef = useRef<HTMLInputElement | null>(null);
  const { value: browserSettings } = useAppSettingsKey('browser');
  const { navigate: navigateToView } = useNavigate();
  const profiles = browserSettings?.profiles ?? DEFAULT_BROWSER_PROFILES;
  const profileLabel = browserProfileLabel(session.profileId, profiles);
  const faviconUrl =
    session.faviconUrl && session.faviconUrl !== failedFaviconUrl ? session.faviconUrl : null;

  useEffect(() => {
    setUrlText(browserUrlInputText(session.currentUrl));
  }, [session.currentUrl]);

  useEffect(() => {
    setFailedFaviconUrl(null);
  }, [session.faviconUrl]);

  useEffect(() => {
    onFocusUrl?.(() => {
      urlInputRef.current?.focus();
      urlInputRef.current?.select();
    });
  }, [onFocusUrl]);

  useEffect(() => {
    if (!autoFocusUrl) return;
    const timer = window.setTimeout(() => {
      urlInputRef.current?.focus();
      urlInputRef.current?.select();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [autoFocusUrl]);

  const navigate = () => {
    navigateTo(urlText);
  };

  const navigateTo = (url: string) => {
    const normalized = normalizeBrowserUrl(url);
    if (!normalized.ok) {
      setUrlError(urlRejectionMessage(normalized.reason));
      return;
    }
    setUrlError(null);
    setUrlText(normalized.url);
    onNavigate?.(normalized.url);
  };

  const openExternal = () => {
    openBrowserUrlExternally(session.currentUrl);
  };

  const openDevTools = () => {
    void getBrowserClient().then((client) => client.openDevTools({ browserId: session.browserId }));
  };

  const confirmClearStorage = () => {
    confirmClearBrowserStorage(session, adapter, profileLabel);
  };

  const switchProfile = (profileId: string) => {
    if (profileId === session.profileId) return;
    browserSessionStore.setSessionProfile(session.browserId, profileId, profiles);
  };

  const takeScreenshot = () => {
    triggerScreenshotSpin();
    void captureBrowserScreenshot(session);
  };

  const canOpenExternal = canOpenBrowserUrlExternally(session.currentUrl);
  const zoomFactor = session.zoomFactor;

  return (
    <div className="flex h-10 shrink-0 items-center gap-1 border-b border-border bg-(--em-surface) px-2">
      <ToolbarIconButton
        label="Back"
        disabled={!adapter || !session.canGoBack}
        onClick={() => onGoBack?.()}
      >
        <ArrowLeft className="size-4" />
      </ToolbarIconButton>
      <ToolbarIconButton
        label="Forward"
        disabled={!adapter || !session.canGoForward}
        onClick={() => onGoForward?.()}
      >
        <ArrowRight className="size-4" />
      </ToolbarIconButton>
      <ToolbarIconButton label={session.isLoading ? 'Stop' : 'Reload'} onClick={() => onReload?.()}>
        {session.isLoading ? <Square className="size-3.5" /> : <RefreshCw className="size-4" />}
      </ToolbarIconButton>
      <form
        className="min-w-0 flex-1"
        onSubmit={(event) => {
          event.preventDefault();
          navigate();
        }}
      >
        <div className="relative">
          {faviconUrl ? (
            <img
              src={faviconUrl}
              alt=""
              className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 rounded-sm"
              draggable={false}
              onError={() => setFailedFaviconUrl(faviconUrl)}
            />
          ) : (
            <Globe className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-foreground-muted" />
          )}
          <Input
            ref={urlInputRef}
            value={urlText}
            onChange={(event) => {
              setUrlText(event.target.value);
              if (urlError) setUrlError(null);
            }}
            onFocus={(event) => event.currentTarget.select()}
            className="h-7 truncate border-0 pr-8 pl-7 text-sm shadow-none hover:border-0 focus-visible:border-0 focus-visible:ring-0"
            aria-label="Browser URL"
            placeholder="Search or enter URL"
            spellCheck={false}
            autoCapitalize="none"
          />
          {session.isLoading && (
            <Loader2 className="pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2 animate-spin text-foreground-muted" />
          )}
        </div>
        {urlError && (
          <div className="sr-only" role="alert">
            {urlError}
          </div>
        )}
      </form>
      <ToolbarIconButton
        label="Copy screenshot"
        disabled={session.currentUrl === BROWSER_DEFAULT_URL || session.isLoading}
        onClick={takeScreenshot}
      >
        <Focus
          className={cn(
            'size-4 transition-transform duration-300 ease-out',
            screenshotSpin && 'rotate-90'
          )}
        />
      </ToolbarIconButton>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger
          render={
            <Button
              type="button"
              variant="ghost"
              icon
              className="size-7 shrink-0"
              aria-label="Browser actions"
            />
          }
        >
          <Ellipsis className="size-4" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Content align="end" className="min-w-56">
          <DropdownMenu.Item disabled={!canOpenExternal} onClick={openExternal}>
            Open externally
          </DropdownMenu.Item>
          <DropdownMenu.Item disabled={!adapter} onClick={() => onForceReload?.()}>
            Force reload
          </DropdownMenu.Item>
          {import.meta.env.DEV && (
            <DropdownMenu.Item onClick={openDevTools}>Open DevTools</DropdownMenu.Item>
          )}
          <DropdownMenu.Separator />
          <DropdownMenu.Sub>
            <DropdownMenu.SubTrigger>Browser profile</DropdownMenu.SubTrigger>
            <DropdownMenu.SubContent className="min-w-44">
              <DropdownMenu.RadioGroup
                value={session.profileId}
                onValueChange={(value) => switchProfile(String(value))}
              >
                {profiles.map((profile) => (
                  <DropdownMenu.RadioItem
                    key={profile.id}
                    value={profile.id}
                    className={PROFILE_RADIO_ITEM_CLASS}
                  >
                    {profile.name}
                  </DropdownMenu.RadioItem>
                ))}
                <DropdownMenu.RadioItem
                  value={BROWSER_ISOLATED_PROFILE_ID}
                  className={PROFILE_RADIO_ITEM_CLASS}
                >
                  Isolated per task
                </DropdownMenu.RadioItem>
              </DropdownMenu.RadioGroup>
              <DropdownMenu.Separator />
              <DropdownMenu.Item
                onClick={() => navigateToView(settingsViewDef({ tab: 'browser' }))}
              >
                Manage profiles…
              </DropdownMenu.Item>
            </DropdownMenu.SubContent>
          </DropdownMenu.Sub>
          <DropdownMenu.Separator />
          <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-sm">
            <span>Zoom</span>
            <div className="flex items-center gap-1">
              <div className="flex items-center rounded-md bg-background-quaternary-1">
                <Button
                  type="button"
                  variant="ghost"
                  icon
                  className="size-6"
                  aria-label="Zoom out"
                  disabled={!canZoomOut(zoomFactor)}
                  onClick={() => onSetZoomFactor?.(previousBrowserZoomFactor(zoomFactor))}
                >
                  <Minus className="size-3.5" />
                </Button>
                <span className="min-w-11 text-center text-xs text-foreground-muted tabular-nums">
                  {formatBrowserZoomPercent(zoomFactor)}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  icon
                  className="size-6"
                  aria-label="Zoom in"
                  disabled={!canZoomIn(zoomFactor)}
                  onClick={() => onSetZoomFactor?.(nextBrowserZoomFactor(zoomFactor))}
                >
                  <Plus className="size-3.5" />
                </Button>
              </div>
              <Button
                type="button"
                variant="ghost"
                icon
                className="size-6"
                aria-label="Reset zoom"
                disabled={isDefaultBrowserZoomFactor(zoomFactor)}
                onClick={() => onSetZoomFactor?.(BROWSER_DEFAULT_ZOOM_FACTOR)}
              >
                <RotateCcw className="size-3.5" />
              </Button>
            </div>
          </div>
          <DropdownMenu.Separator />
          <DropdownMenu.Item
            disabled={!adapter}
            onClick={() => clearBrowserData(session, 'cookies', () => adapter?.reload())}
          >
            Clear cookies
          </DropdownMenu.Item>
          <DropdownMenu.Item
            disabled={!adapter}
            onClick={() => clearBrowserData(session, 'cache', () => adapter?.reloadIgnoringCache())}
          >
            Clear cache
          </DropdownMenu.Item>
          <DropdownMenu.Item onClick={confirmClearStorage}>Clear browser storage</DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    </div>
  );
}

/** Returns a flag that turns on when triggered and resets itself after `durationMs`. */
function useTransientFlag(durationMs: number): [boolean, () => void] {
  const [active, setActive] = useState(false);
  const timerRef = useRef<number | null>(null);

  const trigger = useCallback(() => {
    setActive(true);
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setActive(false), durationMs);
  }, [durationMs]);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  return [active, trigger];
}

function ToolbarIconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <Button
            type="button"
            variant="ghost"
            icon
            className="size-7 shrink-0"
            disabled={disabled}
            aria-label={label}
            onClick={onClick}
          >
            {children}
          </Button>
        }
      />
      <Tooltip.Content>{label}</Tooltip.Content>
    </Tooltip.Root>
  );
}

function urlRejectionMessage(reason: string): string {
  if (reason === 'empty') return 'Enter a URL';
  if (reason === 'unsupported-file-url') return 'File URLs are not enabled for this browser';
  if (reason === 'unsupported-protocol') return 'This URL scheme is not supported';
  return 'Enter a valid URL';
}
