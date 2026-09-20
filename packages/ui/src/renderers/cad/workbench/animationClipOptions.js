// The picker lists authored clips only. Pause holds the frame; Position
// edits return pose ownership to kinematics without an Animation enable switch.
export function animationClipOptions(clips) {
  const authored = Array.isArray(clips) ? clips : [];
  return authored.map((clip) => ({ value: clip.id, label: clip.label }));
}
