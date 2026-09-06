import type { SoundEvent } from '@core/primitives/agents/api';
import type { NotificationSettings } from '@core/primitives/app-settings/api';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { queryClient } from '@core/primitives/query/browser/query-client';
import { getAppSettingsClient } from '@core/services/settings/api/client';

let audioCtx: AudioContext | null = null;
let settings: NotificationSettings = {
  enabled: true,
  sound: true,
  customSoundPath: '',
  osNotifications: true,
  soundFocusMode: 'always',
};
const customAudioCache = new Map<string, string>();
let activePreviewAudio: HTMLAudioElement | null = null;
let activePreviewTones: Array<() => void> = [];
let previewGeneration = 0;
let unsubscribeSettingsCache: (() => void) | null = null;
const recentSounds = new Map<string, number>();

const NOTIFICATIONS_QUERY_KEY = ['appSettings', 'notifications', 'meta'] as const;
const SOUND_DEDUPE_WINDOW_MS = 1_000;

function pruneRecentSounds(now: number): void {
  for (const [key, lastPlayedAt] of recentSounds) {
    if (now - lastPlayedAt >= SOUND_DEDUPE_WINDOW_MS) {
      recentSounds.delete(key);
    }
  }
}

function applySettings(nextSettings: NotificationSettings): void {
  const nextCustomSoundPath = nextSettings.customSoundPath?.trim() ?? '';
  const currentCustomSoundPath = settings.customSoundPath?.trim() ?? '';
  if (nextCustomSoundPath !== currentCustomSoundPath) {
    customAudioCache.clear();
  }
  settings = { ...nextSettings, customSoundPath: nextCustomSoundPath };
}

function applyMeta(meta: unknown): void {
  if (!meta || typeof meta !== 'object' || !('value' in meta)) return;
  applySettings((meta as { value: NotificationSettings }).value);
}

export function initSoundPlayer(): () => void {
  getAppSettingsClient()
    .then((client) => client.getWithMeta({ key: 'notifications' }))
    .then((meta) => {
      queryClient.setQueryData([...NOTIFICATIONS_QUERY_KEY], meta);
      applyMeta(meta);
    })
    .catch(() => {});

  unsubscribeSettingsCache?.();
  const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
    const key = event.query.queryKey;
    if (
      Array.isArray(key) &&
      key[0] === NOTIFICATIONS_QUERY_KEY[0] &&
      key[1] === NOTIFICATIONS_QUERY_KEY[1] &&
      key[2] === NOTIFICATIONS_QUERY_KEY[2]
    ) {
      applyMeta(event.query.state.data);
    }
  });
  unsubscribeSettingsCache = unsubscribe;

  return () => {
    unsubscribe();
    if (unsubscribeSettingsCache === unsubscribe) {
      unsubscribeSettingsCache = null;
    }
  };
}

export function configureSoundPlayer(nextSettings: NotificationSettings): void {
  applySettings(nextSettings);
}

function getContext(): AudioContext {
  if (!audioCtx) {
    audioCtx = new AudioContext();
  }
  return audioCtx;
}

function playTone(
  frequency: number,
  startTime: number,
  duration: number,
  type: OscillatorType = 'triangle',
  gain = 0.15
): () => void {
  const ctx = getContext();
  const osc = ctx.createOscillator();
  const vol = ctx.createGain();
  osc.type = type;
  osc.frequency.value = frequency;
  vol.gain.setValueAtTime(gain, startTime);
  vol.gain.exponentialRampToValueAtTime(0.001, startTime + duration);
  osc.connect(vol);
  vol.connect(ctx.destination);
  osc.start(startTime);
  osc.stop(startTime + duration);
  return () => {
    try {
      osc.stop();
    } catch {
      // Already stopped.
    }
    osc.disconnect();
    vol.disconnect();
  };
}

function playNeedsAttention(): Array<() => void> {
  const ctx = getContext();
  const now = ctx.currentTime;
  return [playTone(880, now, 0.12), playTone(1100, now + 0.15, 0.12)];
}

function playTaskComplete(): Array<() => void> {
  const ctx = getContext();
  const now = ctx.currentTime;
  return [
    playTone(523.25, now, 0.15, 'triangle', 0.12),
    playTone(659.25, now + 0.18, 0.15, 'triangle', 0.12),
    playTone(783.99, now + 0.36, 0.2, 'triangle', 0.12),
  ];
}

async function getCustomSoundDataUrl(path: string): Promise<string | null> {
  let dataUrl = customAudioCache.get(path);
  if (!dataUrl) {
    const result = (await (await getHostClient()).readAudioFileDataUrl({ filePath: path })) as
      | { success: true; dataUrl: string }
      | { success: false; error: string };
    if (!result.success) return null;
    dataUrl = result.dataUrl;
    customAudioCache.set(path, dataUrl);
  }
  return dataUrl;
}

async function playCustomSound(path: string): Promise<boolean> {
  try {
    const dataUrl = await getCustomSoundDataUrl(path);
    if (!dataUrl) return false;
    const audio = new Audio(dataUrl);
    await audio.play();
    return true;
  } catch {
    return false;
  }
}

function playBuiltinSound(event: SoundEvent): Array<() => void> {
  switch (event) {
    case 'needs_attention':
      return playNeedsAttention();
    case 'task_complete':
      return playTaskComplete();
  }
}

function stopActivePreview(): void {
  if (activePreviewAudio) {
    activePreviewAudio.pause();
    activePreviewAudio.currentTime = 0;
    activePreviewAudio = null;
  }
  for (const stopTone of activePreviewTones) {
    stopTone();
  }
  activePreviewTones = [];
}

export const soundPlayer = {
  play(event: SoundEvent, dedupeKey?: string): void {
    if (dedupeKey) {
      const now = Date.now();
      pruneRecentSounds(now);
      const key = `${event}:${dedupeKey}`;
      const lastPlayedAt = recentSounds.get(key);
      if (lastPlayedAt !== undefined && now - lastPlayedAt < SOUND_DEDUPE_WINDOW_MS) return;
      recentSounds.set(key, now);
    }

    try {
      const customSoundPath = settings.customSoundPath?.trim() ?? '';
      if (customSoundPath) {
        void playCustomSound(customSoundPath).then((played) => {
          if (!played) playBuiltinSound(event);
        });
        return;
      }
      playBuiltinSound(event);
    } catch {
      // Audio may fail if user hasn't interacted with page yet
    }
  },

  preview(path?: string): void {
    stopActivePreview();
    const generation = ++previewGeneration;
    const previewPath = path?.trim();

    if (previewPath) {
      void getCustomSoundDataUrl(previewPath)
        .then((dataUrl) => {
          if (generation !== previewGeneration) return;
          if (!dataUrl) {
            activePreviewTones = playBuiltinSound('needs_attention');
            return;
          }

          const audio = new Audio(dataUrl);
          activePreviewAudio = audio;
          audio.addEventListener(
            'ended',
            () => {
              if (activePreviewAudio === audio) activePreviewAudio = null;
            },
            { once: true }
          );
          void audio.play();
        })
        .catch(() => {
          if (generation === previewGeneration) {
            activePreviewTones = playBuiltinSound('needs_attention');
          }
        });
      return;
    }

    activePreviewTones = playBuiltinSound('needs_attention');
  },
};
