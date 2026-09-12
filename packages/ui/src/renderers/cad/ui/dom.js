export function isEditableTarget(target) {
  if (!(target instanceof Element)) {
    return false;
  }
  return !!target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true'], [role='textbox']");
}
