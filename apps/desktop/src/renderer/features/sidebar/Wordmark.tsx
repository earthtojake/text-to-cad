import { useState } from "react";

/**
 * The wordmark, drawn live so it can move: JetBrains Mono ExtraBold Italic,
 * the ink over a copy in the icon's blue offset down-right (the geometry
 * `scripts/make-brand.mjs` renders to PNG). Each letter is its own element in
 * both layers, because the hover effect is per letter: every mouseenter deals
 * each shadow letter a fresh hue, pace and phase for its run through the neon
 * palette, so no two hovers — and no two letters — cycle alike. The ink holds
 * still. `.brand-wordmark` in globals.css does the drawing; `.reduce-motion`
 * stills it.
 */
const TEXT = "HARDCORE";

type Deal = {
  hue: number;
  duration: number;
  delay: number;
};

function deal(): Deal[] {
  return Array.from(TEXT, () => ({
    hue: Math.round(Math.random() * 360),
    duration: 0.9 + Math.random() * 0.9,
    delay: Math.random() * 0.8,
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
            } as React.CSSProperties}
          >
            {letter}
          </span>
        ))}
      </span>
      <span aria-hidden className="brand-wordmark-ink">
        {TEXT}
      </span>
    </span>
  );
}
