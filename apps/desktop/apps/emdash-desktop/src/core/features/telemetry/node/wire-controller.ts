import { createController, type Controller } from '@emdash/wire/rpc';
import type { TelemetryEvent, TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import { telemetryContract } from '@core/primitives/telemetry/api/wire-contract';

export function createTelemetryWireController(telemetry: TelemetryService): Controller {
  return createController(telemetryContract, {
    capture: ({ event, properties }) => {
      telemetry.capture(event as TelemetryEvent, properties);
    },
    getStatus: () => ({ status: telemetry.getTelemetryStatus() }),
    setEnabled: ({ enabled }) => {
      telemetry.setTelemetryEnabledViaUser(enabled);
    },
  });
}
