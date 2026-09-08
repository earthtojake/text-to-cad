import { useState } from "react";

/**
 * The wordmark, drawn live so it can move: JetBrains Mono ExtraBold Italic,
 * the ink over a copy in the icon's blue offset down-right (the geometry
 * `scripts/make-brand.mjs` renders to PNG). Each letter is its own element in
 * both layers, because the hover glitch is per letter: every mouseenter deals
 * each letter a fresh hue, duration, delay and jitter, so no two hovers — and
 * no two letters — run the same loop. `.brand-wordmark` in globals.css does
 * the drawing; `.reduce-motion` stills it.
 */
const TEXT = "HARDCORE";

type Deal = {
  hue: number;
  duration: number;
  delay: number;
  jitterX: number;
  jitterY: number;
  shadowJitter: number;
};

function deal(): Deal[] {
  return Array.from(TEXT, () => ({
    hue: Math.round(Math.random() * 360),
    duration: 0.25 + Math.random() * 0.7,
    delay: Math.random() * 0.5,
    jitterX: (Math.random() - 0.5) * 0.08,
    jitterY: (Math.random() - 0.5) * 0.06,
    shadowJitter: 0.8 + Math.random() * 1.6,
  }));
}

export function Wordmark() {
  const [deals, setDeals] = useState<Deal[]>(deal);
  return (
    <span
      aria-label="Hardcore"
      className="brand-wordmark app-no-drag"
      onMouseEnter={() => setDeals(deal())}
      role="img"
    >
      <span aria-hidden className="brand-wordmark-shadow">
        {Array.from(TEXT, (letter, index) => (
          <span
            key={index}
            style={{
              "--h": `${deals[index]!.hue}deg`,
              "--t": `${deals[index]!.duration.toFixed(2)}s`,
              "--d": `${deals[index]!.delay.toFixed(2)}s`,
              "--k": String(deals[index]!.shadowJitter.toFixed(2)),
            } as React.CSSProperties}
          >
            {letter}
          </span>
        ))}
      </span>
      <span aria-hidden className="brand-wordmark-ink">
        {Array.from(TEXT, (letter, index) => (
          <span
            key={index}
            style={{
              "--t": `${(deals[index]!.duration * 1.3).toFixed(2)}s`,
              "--d": `${deals[index]!.delay.toFixed(2)}s`,
              "--jx": `${deals[index]!.jitterX.toFixed(3)}em`,
              "--jy": `${deals[index]!.jitterY.toFixed(3)}em`,
            } as React.CSSProperties}
          >
            {letter}
          </span>
        ))}
      </span>
    </span>
  );
}
