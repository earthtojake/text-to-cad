import { useCallback, useEffect, useState } from 'react';
import { getTelemetryClient } from './telemetry-client';

type TelemetryState = {
  prefEnabled: boolean;
  envDisabled: boolean;
  hasKeyAndHost: boolean;
  loading: boolean;
};

type TelemetryStatusResponse = {
  status: {
    envDisabled: boolean;
    userOptOut: boolean;
    hasKeyAndHost: boolean;
  };
};

const initialState: TelemetryState = {
  prefEnabled: true,
  envDisabled: false,
  hasKeyAndHost: true,
  loading: true,
};

export function useTelemetryConsent() {
  const [state, setState] = useState<TelemetryState>(initialState);

  const applyStatus = useCallback((res: TelemetryStatusResponse | null) => {
    if (res?.status) {
      const { envDisabled: envOff, userOptOut, hasKeyAndHost } = res.status;
      setState({
        prefEnabled: !envOff && userOptOut !== true,
        envDisabled: !!envOff,
        hasKeyAndHost: !!hasKeyAndHost,
        loading: false,
      });
    } else {
      setState((prev) => ({ ...prev, loading: false }));
    }
  }, []);

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true }));
    try {
      applyStatus(await (await getTelemetryClient()).getStatus());
    } catch {
      setState((prev) => ({ ...prev, loading: false }));
    }
  }, [applyStatus]);

  const setTelemetryEnabled = useCallback(
    async (enabled: boolean) => {
      setState((prev) => ({ ...prev, prefEnabled: enabled, loading: true }));
      try {
        await (await getTelemetryClient()).setEnabled({ enabled });
      } catch {
        // ignore, refresh will reconcile
      }
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    let cancelled = false;
    getTelemetryClient()
      .then((client) => client.getStatus())
      .then((res) => {
        if (!cancelled) applyStatus(res);
      })
      .catch(() => {
        if (!cancelled) setState((prev) => ({ ...prev, loading: false }));
      });
    return () => {
      cancelled = true;
    };
  }, [applyStatus]);

  return {
    ...state,
    refresh,
    setTelemetryEnabled,
  };
}
