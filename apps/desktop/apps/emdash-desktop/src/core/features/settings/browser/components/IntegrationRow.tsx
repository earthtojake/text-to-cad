import { Tooltip } from '@emdash/ui/react/primitives';
import { Check, Copy, ExternalLink, Trash2 } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { useTheme } from '@core/primitives/theme/browser';

type IntegrationStatus =
  | 'connected'
  | 'disconnected'
  | 'loading'
  | 'error'
  | 'missing'
  | 'needs_key';

interface IntegrationRowProps {
  logoSrc?: string;
  logoSrcDark?: string;
  invertInDark?: boolean;
  icon?: React.ReactNode;
  name: string;
  onNameClick?: () => void;
  status: IntegrationStatus;
  statusLabel?: string;
  accountLabel?: string;
  middle?: React.ReactNode;
  onConnect?: () => void;
  connectDisabled?: boolean;
  connectContent?: React.ReactNode;
  onDisconnect?: () => void;
  onOpen?: () => void;
  rightExtra?: React.ReactNode;
  showStatusPill?: boolean;
  installCommand?: string | null;
}

const STATUS_CLASSES: Record<IntegrationStatus, string> = {
  connected: 'border border-border-success bg-background-success text-foreground-success',
  loading: 'border border-border/60 bg-transparent text-foreground-muted',
  error: 'border border-border/60 bg-transparent text-foreground-muted',
  disconnected: 'border border-border/60 bg-transparent text-foreground-muted',
  missing: 'border border-border/60 bg-transparent text-foreground-muted',
  needs_key: 'border border-border/60 bg-transparent text-foreground-muted',
};

const STATUS_LABELS: Record<IntegrationStatus, string> = {
  connected: 'Connected',
  loading: 'Connecting…',
  error: 'Not connected',
  disconnected: 'Not connected',
  missing: 'Not connected',
  needs_key: 'Not connected',
};

const BUTTON_BASE =
  'inline-flex h-8 min-w-[2.5rem] items-center justify-center rounded-md border border-border/70 bg-background px-2.5 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-60';

const ICON_BUTTON =
  'rounded-md p-1.5 text-foreground-muted transition hover:bg-background-2/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background';

const ICON_WRAPPER =
  'flex h-6 w-6 items-center justify-center rounded-md bg-background-2/40 text-foreground-muted';

/** Logo wrapper without background - logos render directly. */
const LOGO_WRAPPER = 'flex h-6 w-6 items-center justify-center';

const IntegrationRow: React.FC<IntegrationRowProps> = ({
  logoSrc,
  logoSrcDark,
  invertInDark,
  icon,
  name,
  onNameClick,
  status,
  statusLabel,
  accountLabel,
  middle,
  onConnect,
  connectDisabled,
  connectContent,
  onDisconnect,
  onOpen,
  rightExtra,
  showStatusPill = true,
  installCommand,
}) => {
  const { effectiveTheme } = useTheme();
  const isDark = effectiveTheme === 'emdark';
  const themedLogoSrc = isDark && logoSrcDark ? logoSrcDark : logoSrc;
  const shouldInvertLogo = isDark && !!invertInDark && !logoSrcDark;
  const resolvedStatus = STATUS_CLASSES[status] ? status : 'disconnected';
  const showConnect = resolvedStatus !== 'connected' && status !== 'loading' && !!onConnect;
  const showDisconnect = resolvedStatus === 'connected' && !!onDisconnect;
  const showOpen = resolvedStatus === 'connected' && !!onOpen;
  const [copied, setCopied] = useState(false);
  const copyResetRef = useRef<number | null>(null);

  const resolvedStatusLabel = statusLabel ?? STATUS_LABELS[status] ?? STATUS_LABELS.disconnected;

  const defaultMiddle =
    status === 'connected' && accountLabel ? (
      <span className="truncate text-sm text-foreground-muted">{accountLabel}</span>
    ) : null;

  const isSvg = themedLogoSrc?.trimStart().startsWith('<svg');

  const avatar = (
    <span className={themedLogoSrc ? LOGO_WRAPPER : ICON_WRAPPER}>
      {themedLogoSrc ? (
        isSvg ? (
          <span
            className={`${shouldInvertLogo ? 'invert' : ''} inline-flex h-5 w-5 items-center justify-center [&_svg]:h-full [&_svg]:w-full [&_svg]:shrink-0`}
            dangerouslySetInnerHTML={{ __html: themedLogoSrc }}
          />
        ) : (
          <img
            src={themedLogoSrc}
            alt=""
            className={`${shouldInvertLogo ? 'invert' : ''} h-5 w-5 object-contain`}
          />
        )
      ) : icon ? (
        icon
      ) : null}
    </span>
  );

  const handleCopyInstall = async () => {
    if (!installCommand || typeof navigator === 'undefined' || !navigator.clipboard) {
      return;
    }
    if (copyResetRef.current !== null) {
      window.clearTimeout(copyResetRef.current);
    }
    try {
      await navigator.clipboard.writeText(installCommand);
      setCopied(true);
      copyResetRef.current = window.setTimeout(() => {
        setCopied(false);
        copyResetRef.current = null;
      }, 1600);
    } catch {
      setCopied(false);
      copyResetRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      if (copyResetRef.current !== null) {
        window.clearTimeout(copyResetRef.current);
      }
    };
  }, []);

  const CopyIcon = copied ? Check : Copy;
  const showInstallCopy = !!installCommand && status !== 'connected';

  return (
    <div className="group relative grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-background-2/40">
      <div className="flex items-center gap-3">
        {avatar}
        {onNameClick ? (
          <button
            type="button"
            onClick={onNameClick}
            className="group flex items-center gap-1 text-sm font-medium text-foreground transition focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none"
          >
            <span>{name}</span>
            <span className="text-xs text-foreground-muted transition group-hover:text-foreground/80">
              ↗
            </span>
          </button>
        ) : (
          <span className="text-sm font-medium text-foreground">{name}</span>
        )}
      </div>

      <div className="flex items-center justify-end gap-2 text-sm text-foreground-muted">
        {showInstallCopy ? (
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger
                render={
                  <button
                    type="button"
                    onClick={() => {
                      void handleCopyInstall();
                    }}
                    className={ICON_BUTTON}
                    aria-label={copied ? 'Command copied' : `Copy install command for ${name}`}
                  >
                    <CopyIcon className="h-4 w-4" aria-hidden="true" />
                  </button>
                }
              />
              <Tooltip.Content side="top">
                <div className="max-w-[240px] space-y-1">
                  <div className="text-xs font-medium text-foreground">Copy install command</div>
                  <code className="block truncate font-mono text-tiny text-foreground-muted">
                    {installCommand}
                  </code>
                </div>
              </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
        ) : null}

        <div className="min-w-0">{middle ?? defaultMiddle}</div>
        {showStatusPill ? (
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-micro font-medium tracking-[1.25px] uppercase ${STATUS_CLASSES[resolvedStatus] ?? STATUS_CLASSES.disconnected}`}
          >
            {resolvedStatusLabel}
          </span>
        ) : null}

        {rightExtra}

        {showOpen ? (
          <button
            type="button"
            onClick={onOpen}
            className={ICON_BUTTON}
            aria-label={`Open ${name} settings`}
          >
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}

        {showDisconnect ? (
          <button
            type="button"
            onClick={onDisconnect}
            className={ICON_BUTTON}
            aria-label={`Disconnect ${name}`}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}

        {showConnect ? (
          <button
            type="button"
            onClick={onConnect}
            className={BUTTON_BASE}
            disabled={connectDisabled}
          >
            {connectContent ?? 'Connect'}
          </button>
        ) : null}
      </div>
    </div>
  );
};

export default IntegrationRow;
