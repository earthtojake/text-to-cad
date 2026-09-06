import type { AppNotification } from './schemas';

export type NotificationRoutingSettings = {
  enabled: boolean;
  sound: boolean;
  osNotifications: boolean;
  soundFocusMode: 'always' | 'unfocused';
};

export type RoutingContext = {
  appFocused: boolean;
  settings: NotificationRoutingSettings;
};

export type RoutingDecision = {
  system: boolean;
  sound: boolean;
};

export type RoutingPolicy = (
  notification: AppNotification,
  context: RoutingContext
) => RoutingDecision;

export const defaultRoutingPolicy: RoutingPolicy = (notification, context) => {
  if (!context.settings.enabled) return { system: false, sound: false };
  if (notification.kind === 'update-error' || notification.kind === 'update-available') {
    return { system: false, sound: false };
  }

  return {
    system: context.settings.osNotifications && !context.appFocused,
    sound:
      notification.sound !== null &&
      context.settings.sound &&
      (context.settings.soundFocusMode === 'always' || !context.appFocused),
  };
};
