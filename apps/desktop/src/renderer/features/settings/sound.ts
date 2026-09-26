/**
 * The notification sound, and the Preview button beside it.
 *
 * Hardcore's own sound is synthesised rather than shipped as an asset: two
 * short sine tones are a smaller, more reviewable thing than a wav file in the
 * repository, and the point of the preview is to answer "is this audible where
 * I am sitting", which a chime answers as well as anything.
 *
 * A custom file is played through an ordinary `Audio` element pointed at
 * `file://`. That can fail — the renderer's origin is `http://127.0.0.1` in
 * development, which is not allowed to load a local file — so the chime is the
 * fallback rather than a silent failure.
 */

/** Play the user's sound: their file if they chose one, otherwise the chime. */
export async function playNotificationSound(file: string | null): Promise<void> {
  if (file) {
    try {
      await playFile(file);
      return;
    } catch {
      // Fall through: an unreadable file should still make a noise, so the
      // Preview button never looks broken.
    }
  }
  playChime();
}

function playFile(file: string): Promise<void> {
  const url = `file://${file.split("/").map(encodeURIComponent).join("/")}`;
  const audio = new Audio(url);
  audio.volume = 0.6;
  return audio.play();
}

/** Two notes, a fifth apart, 260 ms in total. */
function playChime() {
  const AudioCtor = window.AudioContext;
  if (!AudioCtor) {
    return;
  }
  const context = new AudioCtor();
  const now = context.currentTime;
  [
    { frequency: 880, at: 0 },
    { frequency: 1320, at: 0.11 },
  ].forEach(({ frequency, at }) => {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = frequency;
    // An envelope, not a square edge: a gain that jumps to full clicks.
    gain.gain.setValueAtTime(0.0001, now + at);
    gain.gain.exponentialRampToValueAtTime(0.22, now + at + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.15);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(now + at);
    oscillator.stop(now + at + 0.16);
  });
  // Closing releases the audio device; leaving contexts open costs one per press.
  window.setTimeout(() => void context.close(), 600);
}
