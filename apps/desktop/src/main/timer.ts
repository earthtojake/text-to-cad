/** `fire` after `ms`, and the function that cancels it. */
export function startTimer(ms: number, fire: () => void): () => void {
  const handle = setTimeout(fire, ms);
  return () => clearTimeout(handle);
}
