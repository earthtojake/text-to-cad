import { Button, Switch } from '@emdash/ui/react/primitives';
import { ArrowUpRight } from 'lucide-react';
import React from 'react';
import { PRODUCT_NAME } from '@core/primitives/app-identity/api/app-identity';
import { openExternal } from '@core/primitives/desktop-host/browser/host-client';
import { captureTelemetry } from '@core/primitives/telemetry/browser/telemetry-client';
import { useTelemetryConsent } from '@core/primitives/telemetry/browser/useTelemetryConsent';
import { SettingRow } from './SettingRow';

const TelemetryCard: React.FC = () => {
  const { prefEnabled, envDisabled, hasKeyAndHost, loading, setTelemetryEnabled } =
    useTelemetryConsent();

  return (
    <SettingRow
      title="Privacy & Telemetry"
      description={
        <div>
          <p>Help improve {PRODUCT_NAME} by sending anonymous usage data.</p>
          <p>
            <span>See </span>
            <Button
              type="button"
              variant="link"
              size="sm"
              className="group inline-flex h-auto items-center gap-1 px-0 text-sm font-normal text-foreground-muted hover:text-foreground hover:no-underline focus-visible:ring-0 focus-visible:outline-none"
              onClick={() => openExternal('https://github.com/amywork777/hardcore')}
            >
              <span className="transition-colors group-hover:text-foreground">
                Telemetry information
              </span>
              <ArrowUpRight className="size-3.5 text-foreground-muted transition-colors transition-transform duration-200 group-hover:translate-x-px group-hover:-translate-y-px group-hover:text-foreground" />
            </Button>
            <span> for details.</span>
          </p>
        </div>
      }
      control={
        <div className="flex flex-col items-end gap-1">
          <Switch
            checked={prefEnabled}
            onCheckedChange={(checked) => {
              captureTelemetry('setting_changed', { setting: 'telemetry' });
              void setTelemetryEnabled(checked);
            }}
            disabled={loading || envDisabled}
            aria-label="Enable anonymous telemetry"
          />
          {!hasKeyAndHost && (
            <span className="text-micro text-foreground-muted">
              Inactive in this build (no PostHog keys)
            </span>
          )}
        </div>
      }
    />
  );
};

export default TelemetryCard;
