import { useEffect, useState } from 'react';

export function useDelayedBoolean(value: boolean, delayMs: number): boolean {
  const [delayed, setDelayed] = useState(false);
  useEffect(() => {
    const delay = value ? delayMs : 0;
    const timer = setTimeout(() => setDelayed(value), delay);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return delayed;
}
