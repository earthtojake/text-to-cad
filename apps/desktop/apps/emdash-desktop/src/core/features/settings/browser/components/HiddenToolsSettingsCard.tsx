import { SettingsCard } from '@emdash/ui/react/patterns';
import { Switch, Tooltip } from '@emdash/ui/react/primitives';
import { useMemo } from 'react';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { useOpenInApps } from '@core/features/settings/api/browser/useOpenInApps';
import { OPEN_IN_APPS, type OpenInAppId } from '@core/primitives/open-in-apps/api/open-in-apps';
import IntegrationRow from './IntegrationRow';

export default function HiddenToolsSettingsCard() {
  const { value: openIn, update, isLoading, isSaving } = useAppSettingsKey('openIn');
  const { icons, labels, availability } = useOpenInApps();

  const hiddenApps: OpenInAppId[] = openIn?.hidden ?? [];

  const toggle = (appId: OpenInAppId, visible: boolean) => {
    const next = visible ? hiddenApps.filter((id) => id !== appId) : [...hiddenApps, appId];
    update({ hidden: next });
  };

  const sortedApps = useMemo(() => {
    return Object.values(OPEN_IN_APPS).sort((a, b) => {
      const aDetected = availability[a.id] ?? a.alwaysAvailable ?? false;
      const bDetected = availability[b.id] ?? b.alwaysAvailable ?? false;
      if (aDetected && !bDetected) return -1;
      if (!aDetected && bDetected) return 1;
      return (labels[a.id] ?? a.label).localeCompare(labels[b.id] ?? b.label);
    });
  }, [availability, labels]);

  return (
    <SettingsCard>
      <div className="space-y-2">
        {sortedApps.map((app) => {
          const isDetected = availability[app.id] ?? app.alwaysAvailable ?? false;
          const isVisible = isDetected && !hiddenApps.includes(app.id);
          const canToggleVisibility = isDetected;
          const label = labels[app.id] ?? app.label;
          const icon = icons[app.id];
          const indicatorClass = isDetected ? 'bg-foreground-success' : 'bg-foreground-passive/50';
          const statusLabel = isDetected ? 'Detected' : 'Not detected';

          return (
            <IntegrationRow
              key={app.id}
              logoSrc={icon}
              name={label}
              status={isDetected ? 'connected' : 'missing'}
              showStatusPill={false}
              middle={
                <span className="flex items-center gap-2 text-sm text-foreground-muted">
                  <span className={`h-1.5 w-1.5 rounded-full ${indicatorClass}`} />
                  {statusLabel}
                </span>
              }
              rightExtra={
                <Tooltip.Provider delay={150}>
                  <Tooltip.Root>
                    <Tooltip.Trigger
                      render={
                        <span>
                          <Switch
                            checked={isVisible}
                            disabled={isLoading || isSaving || !canToggleVisibility}
                            onCheckedChange={(checked) => toggle(app.id, checked)}
                            aria-label={`${isVisible ? 'Hide' : 'Show'} ${label} in open menu`}
                          />
                        </span>
                      }
                    />
                    <Tooltip.Content side="top" className="text-xs">
                      {!isDetected
                        ? 'Install this tool to show it in menu'
                        : isVisible
                          ? 'Hide from menu'
                          : 'Show in menu'}
                    </Tooltip.Content>
                  </Tooltip.Root>
                </Tooltip.Provider>
              }
            />
          );
        })}
      </div>
    </SettingsCard>
  );
}
