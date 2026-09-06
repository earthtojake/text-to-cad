import { Tooltip } from '@emdash/ui/react/primitives';
import { QueryClientProvider } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';
import { GithubContextProvider } from '@core/features/github/api/browser/github-context-provider';
import { TerminalPoolProvider } from '@core/features/terminals/browser/pty/pty-pool-provider';
import { confirmOpenExternalLink } from '@core/features/workbench/api/browser/open-external-link';
import { FramelessTitlebarOverlay } from '@core/features/workbench/browser/window-controls';
import { WorkspaceLayoutContextProvider } from '@core/features/workbench/contributions/browser/layout-provider';
import { ExternalLinkProvider } from '@core/primitives/external-links/browser';
import { queryClient } from '@core/primitives/query/browser/query-client';
import { HostRecoveryWakeups } from '@core/services/hosts/browser/recovery-wakeups';
import { AppMenuEvents } from './app/app-menu-events';
import { AppShutdownLifecycle } from './app/app-shutdown-lifecycle';
import { WelcomeScreen } from './app/welcome';
import { Workspace } from './app/workspace';
import { WorkspaceViewProvider } from './lib/layout/provider';
import { ModalRenderer } from './lib/modal/modal-renderer';
import { ThemeProvider } from './lib/providers/theme-provider';

export const HAS_SEEN_ONBOARDING = 'hardcore:has-seen-onboarding:v1';
const LEGACY_HAS_SEEN_ONBOARDING = 'emdash:has-seen-onboarding:v1';

function hasSeenOnboarding(): boolean {
  const seen =
    localStorage.getItem(HAS_SEEN_ONBOARDING) ?? localStorage.getItem(LEGACY_HAS_SEEN_ONBOARDING);
  if (seen === 'true') localStorage.setItem(HAS_SEEN_ONBOARDING, 'true');
  return seen === 'true';
}

type AppView = 'welcome' | 'workspace';

function AppContent() {
  const [view, setView] = useState<AppView>(() => (hasSeenOnboarding() ? 'workspace' : 'welcome'));

  useEffect(() => {
    localStorage.setItem(HAS_SEEN_ONBOARDING, 'true');
  }, []);

  const handleOpenSettingsFromMenu = useCallback(() => {
    setView('workspace');
    return true;
  }, []);

  const renderContent = () => {
    // The welcome splash is an opaque full-screen overlay, so the Workspace
    // would be fully hidden behind it; render it standalone to avoid mounting a
    // second, hidden WindowControls (the Workspace Titlebar's) underneath.
    if (view === 'welcome') {
      return (
        <>
          <WelcomeScreen onGetStarted={() => window.location.reload()} />
          <FramelessTitlebarOverlay />
        </>
      );
    }
    return <Workspace />;
  };

  return (
    <Tooltip.Provider delay={300}>
      <WorkspaceLayoutContextProvider>
        <TerminalPoolProvider>
          <GithubContextProvider>
            <WorkspaceViewProvider>
              <AppMenuEvents onOpenSettings={handleOpenSettingsFromMenu} />
              <ExternalLinkProvider openExternalLink={confirmOpenExternalLink}>
                <ThemeProvider>
                  <ModalRenderer />
                  <AppShutdownLifecycle />
                  <HostRecoveryWakeups />
                  {renderContent()}
                </ThemeProvider>
              </ExternalLinkProvider>
            </WorkspaceViewProvider>
          </GithubContextProvider>
        </TerminalPoolProvider>
      </WorkspaceLayoutContextProvider>
    </Tooltip.Provider>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}
