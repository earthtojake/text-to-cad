/**
 * Simple telemetry client for the browser side.
 * Captures events and sends them to the main process over the wire.
 */
import type { ContractClient } from '@emdash/wire/rpc';
import type { TelemetryEvent, TelemetryProperties } from '@core/primitives/telemetry/api/telemetry';
import { telemetryContract, telemetryDomain } from '@core/primitives/telemetry/api/wire-contract';
import { focusTracker } from '@core/primitives/telemetry/browser/focus-tracker';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { getTelemetryScope } from './telemetry-scope';

export type TelemetryClient = ContractClient<typeof telemetryContract>;

export function getTelemetryClient(): Promise<TelemetryClient> {
  return domainClient<TelemetryClient>(telemetryDomain, telemetryContract);
}

let cachedSessionId: string | null | undefined;
let pendingSessionIdPromise: Promise<string | null> | null = null;

async function getSessionId(): Promise<string | null> {
  if (cachedSessionId !== undefined) return cachedSessionId;
  if (pendingSessionIdPromise) return pendingSessionIdPromise;

  pendingSessionIdPromise = getTelemetryClient()
    .then((client) => client.getStatus())
    .then((result) => {
      cachedSessionId = result.status?.session_id ?? null;
      return cachedSessionId;
    })
    .catch(() => {
      return null;
    })
    .finally(() => {
      pendingSessionIdPromise = null;
    });

  return pendingSessionIdPromise;
}

async function captureWithProps(event: TelemetryEvent, properties?: Record<string, unknown>) {
  const sessionId = await getSessionId();

  void getTelemetryClient()
    .then((client) =>
      client.capture({
        event,
        properties: {
          ...(properties ?? {}),
          ...getTelemetryScope(),
          ...(sessionId ? { session_id: sessionId } : {}),
        },
      })
    )
    .catch(() => {});
}

export function captureTelemetry<E extends TelemetryEvent>(
  event: E,
  properties?: TelemetryProperties<E>
): void {
  void captureWithProps(event, {
    ...focusTracker.getContext(),
    ...(properties as Record<string, unknown> | undefined),
  }).catch(() => {
    // Telemetry failures never break the app
  });
}

focusTracker.setTransitionEmitter((properties) => {
  captureTelemetry('focus_changed', properties);
});
