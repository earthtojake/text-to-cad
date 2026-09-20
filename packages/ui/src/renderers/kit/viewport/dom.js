export function isEditableTarget(target) {
  if (!(target instanceof Element)) {
    return false;
  }
  return !!target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true'], [role='textbox']");
}

export function cssLength(value, fallback = "0px") {
  if (typeof value === "number" && Number.isFinite(value)) {
    return `${value}px`;
  }
  const text = String(value || "").trim();
  return text || fallback;
}

export function isPointerInsideElement(event, element) {
  if (!event || !element || !Number.isFinite(Number(event.clientX)) || !Number.isFinite(Number(event.clientY))) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return (
    event.clientX >= rect.left &&
    event.clientX <= rect.right &&
    event.clientY >= rect.top &&
    event.clientY <= rect.bottom
  );
}
