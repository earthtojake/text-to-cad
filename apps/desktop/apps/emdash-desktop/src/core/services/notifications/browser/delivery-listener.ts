import type { SoundEvent } from '@core/primitives/agents/api';
import { runNotificationOpenHandler } from '@core/primitives/notifications/browser/open-handlers';
import { getNotificationsClient } from '@core/services/notifications/api/client';

/** Plays a notification sound; injected by the host bootstrap (sound playback lives outside this service). */
export type PlayNotificationSound = (sound: SoundEvent, dedupeKey?: string) => void;

let cleanup: (() => void) | null = null;

export function initNotificationDeliveryListener(playSound: PlayNotificationSound): () => void {
  if (cleanup) return cleanup;

  let disposed = false;
  let unsubscribe: (() => void) | null = null;

  void getNotificationsClient()
    .then((client) =>
      client.delivery.subscribe(undefined, {
        onEvent(event) {
          if (event.type === 'sound') {
            playSound(event.sound, event.notificationId);
          } else {
            runNotificationOpenHandler(event.target, event.notificationId);
          }
        },
        onGap() {},
        onError() {},
      })
    )
    .then((nextUnsubscribe) => {
      if (disposed) {
        nextUnsubscribe();
        return;
      }
      unsubscribe = nextUnsubscribe;
    })
    .catch(() => {});

  cleanup = () => {
    disposed = true;
    unsubscribe?.();
    unsubscribe = null;
    cleanup = null;
  };
  return cleanup;
}
