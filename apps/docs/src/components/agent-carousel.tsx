"use client";

import Image from "next/image";
import { useEffect, useRef } from "react";
import { agents } from "@/lib/content";

/**
 * The agents' logos, drifting sideways as skills.sh's do, as a strip you can also move yourself:
 * two copies side by side in a scroll container, so passing the first copy's width puts it back at
 * the start unseen. It drifts a copy's width in 110 seconds and rests while a mouse is over it, a
 * finger is on it or focus is in it, and while it is off screen. A vertical wheel over it scrolls the
 * page, never the strip: a trackpad's sideways swipe or Shift with the wheel moves it, as the browser
 * scrolls any sideways list, a mouse drags it, a finger swipes it, and the arrow keys move it once
 * focused. Anyone who asks for less motion gets one still copy that scrolls the same ways. Each tile
 * is a black square: it takes the page's own colour, lightened into the dark theme and, inverted,
 * darkened into the light one. The logos are not links: Install, below, covers them all; their names
 * are the captions under them, so the pictures themselves say nothing to a screen reader.
 */
const DRIFT_SECONDS = 110;

export function AgentCarousel() {
  const strip = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = strip.current;
    if (!el) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const half = () => (reduced ? Infinity : el.scrollWidth / 2);
    // The drift runs only while it moves something: never under reduced motion, not while it rests
    // (a mouse over it, a finger on it, focus in it) and not while the strip is off screen.
    let resting = false;
    let visible = false;
    let pos = el.scrollLeft;
    let last = 0;
    let frame = 0;

    const tick = (now: number) => {
      const dt = last ? Math.min(now - last, 100) : 0;
      last = now;
      // Someone else moved it (swipe, Shift and the wheel, drag, keys): follow them rather than fight.
      if (Math.abs(el.scrollLeft - pos) > 1.5) pos = el.scrollLeft;
      pos += (half() / DRIFT_SECONDS) * (dt / 1000);
      if (pos >= half()) pos -= half();
      el.scrollLeft = pos;
      frame = requestAnimationFrame(tick);
    };
    const drift = () => {
      const moving = !reduced && visible && !resting;
      if (moving && !frame) {
        last = 0;
        pos = el.scrollLeft;
        frame = requestAnimationFrame(tick);
      } else if (!moving && frame) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
    };
    const seen = new IntersectionObserver(([entry]) => {
      visible = Boolean(entry?.isIntersecting);
      drift();
    });
    seen.observe(el);

    const onScroll = () => {
      if (el.scrollLeft >= half()) el.scrollLeft -= half();
    };
    let dragFrom: { x: number; left: number } | null = null;
    const onDown = (event: PointerEvent) => {
      if (event.pointerType !== "mouse" || event.button !== 0) return;
      dragFrom = { x: event.clientX, left: el.scrollLeft };
      el.setPointerCapture(event.pointerId);
      el.dataset.dragging = "true";
    };
    const onMove = (event: PointerEvent) => {
      if (!dragFrom) return;
      el.scrollLeft = Math.max(0, dragFrom.left - (event.clientX - dragFrom.x));
      pos = el.scrollLeft;
    };
    const onUp = () => {
      dragFrom = null;
      delete el.dataset.dragging;
    };
    const rest = () => { resting = true; drift(); };
    const go = () => { resting = false; drift(); };
    // A mouse over it rests it; a tap's pointer is no mouse, so a finger lifted lets it drift again.
    const onEnter = (event: PointerEvent) => { if (event.pointerType === "mouse") rest(); };
    const onLeave = (event: PointerEvent) => { if (event.pointerType === "mouse") go(); };
    const onFocusOut = (event: FocusEvent) => {
      if (!el.contains(event.relatedTarget as Node | null)) go();
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
    el.addEventListener("pointerenter", onEnter);
    el.addEventListener("pointerleave", onLeave);
    el.addEventListener("touchstart", rest, { passive: true });
    el.addEventListener("touchend", go, { passive: true });
    el.addEventListener("focusin", rest);
    el.addEventListener("focusout", onFocusOut);
    return () => {
      seen.disconnect();
      cancelAnimationFrame(frame);
      el.removeEventListener("scroll", onScroll);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onUp);
      el.removeEventListener("pointerenter", onEnter);
      el.removeEventListener("pointerleave", onLeave);
      el.removeEventListener("touchstart", rest);
      el.removeEventListener("touchend", go);
      el.removeEventListener("focusin", rest);
      el.removeEventListener("focusout", onFocusOut);
    };
  }, []);

  const logos = (copy: number) => (
    <ul className={copy ? "flex shrink-0 motion-reduce:hidden" : "flex shrink-0"} aria-hidden={copy ? true : undefined}>
      {agents.map((agent) => (
        <li key={agent.logo} title={agent.name} className="flex select-none flex-col items-center gap-1 px-1">
          <Image
            src={`/agents/${agent.logo}.svg`}
            alt=""
            width={100}
            height={100}
            unoptimized
            draggable={false}
            className="h-[72px] w-auto invert mix-blend-darken [@media(min-width:64rem)_and_(min-height:44rem)]:h-[88px] dark:invert-0 dark:mix-blend-lighten"
          />
          <span className="whitespace-nowrap text-center text-xs leading-4 text-muted-foreground">{agent.name}</span>
        </li>
      ))}
    </ul>
  );
  return (
    <div className="[mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)] has-[:focus-visible]:[mask-image:none]">
      <div
        ref={strip}
        role="region"
        aria-label="Agents text-to-cad works with"
        tabIndex={0}
        className="flex cursor-grab overflow-x-auto overscroll-x-contain bg-background [scrollbar-width:none] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring data-[dragging=true]:cursor-grabbing [&::-webkit-scrollbar]:hidden"
      >
        {logos(0)}
        {logos(1)}
      </div>
    </div>
  );
}
