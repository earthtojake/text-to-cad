import { awaitWirePort, connect, domPortTransport, type DomPortLike } from '@emdash/wire/rpc';
import { DESKTOP_WIRE_CHANNEL } from '@core/manifests/shared/wire-channels';
import { resetWireConnection, seedWireConnection } from '@core/primitives/wire/browser/connection';

/**
 * The production seed: called once by the renderer bootstrap before React mounts.
 * This is the only host-owned wire code — port acquisition over the Electron
 * preload bridge. Everything downstream reaches the wire through the core seam.
 */
export function seedDesktopWire(): void {
  seedWireConnection(async () => {
    const portPromise = awaitWirePort(window, { channel: DESKTOP_WIRE_CHANNEL });
    await window.electronAPI.requestWirePort(DESKTOP_WIRE_CHANNEL);
    return connect(domPortTransport((await portPromise) as DomPortLike));
  });
}

// Dev-server edits to seeding modules must not leave a stale connection behind.
import.meta.hot?.dispose(() => resetWireConnection());
