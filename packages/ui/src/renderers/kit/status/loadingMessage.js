// What a long wait says about itself, under the loading mark.
export function prolongedLoadingMessage(elapsedMs, connectionLost = null) {
  if (connectionLost) return "Waiting for a response. Retrying…";
  if (elapsedMs < 10_000) return "";
  const seconds = Math.floor(elapsedMs / 1000);
  return `${seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`} elapsed`;
}
