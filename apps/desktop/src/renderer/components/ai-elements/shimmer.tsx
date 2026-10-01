"use client";

import { cn } from "@renderer/lib/utils";
import type { MotionProps } from "motion/react";
import { motion, useReducedMotionConfig } from "motion/react";
import type { CSSProperties, ElementType, JSX } from "react";
import { memo, useMemo } from "react";

type MotionHTMLProps = MotionProps & Record<string, unknown>;

// Cache motion components at module level to avoid creating during render
const motionComponentCache = new Map<
  keyof JSX.IntrinsicElements,
  React.ComponentType<MotionHTMLProps>
>();

const getMotionComponent = (element: keyof JSX.IntrinsicElements) => {
  let component = motionComponentCache.get(element);
  if (!component) {
    component = motion.create(element);
    motionComponentCache.set(element, component);
  }
  return component;
};

export interface TextShimmerProps {
  children: string;
  as?: ElementType;
  className?: string;
  duration?: number;
  spread?: number;
}

const ShimmerComponent = ({
  children,
  as: Component = "p",
  className,
  duration = 2,
  spread = 2,
}: TextShimmerProps) => {
  const MotionComponent = getMotionComponent(
    Component as keyof JSX.IntrinsicElements
  );

  // Deliberate edit to the vendored component: motion's own reduced-motion
  // setting only turns off transforms and layout, and this animates a
  // background-position, so the sweep would run on under "Reduce motion".
  // The window's MotionConfig (App) carries the setting, the OS is its
  // fallback, and a reduced sweep is the still band.
  const reduced = useReducedMotionConfig();

  const dynamicSpread = useMemo(
    () => (children?.length ?? 0) * spread,
    [children, spread]
  );

  return (
    <MotionComponent
      animate={reduced ? undefined : { backgroundPosition: "0% center" }}
      className={cn(
        "relative inline-block bg-[length:250%_100%,auto] bg-clip-text text-transparent",
        // Deliberate edit to the vendored component: the band is the
        // foreground, not the background. A background-coloured band erases
        // the letters it passes over — the first letter of "Editing hello.py"
        // vanished in every streaming screenshot — where a brighter band reads
        // as the shimmer it is meant to be.
        "[--bg:linear-gradient(90deg,#0000_calc(50%-var(--spread)),var(--color-foreground),#0000_calc(50%+var(--spread)))] [background-repeat:no-repeat,padding-box]",
        className
      )}
      initial={reduced ? false : { backgroundPosition: "100% center" }}
      style={
        {
          "--spread": `${dynamicSpread}px`,
          backgroundImage:
            "var(--bg), linear-gradient(var(--color-muted-foreground), var(--color-muted-foreground))",
        } as CSSProperties
      }
      transition={
        reduced
          ? undefined
          : {
              duration,
              ease: "linear",
              repeat: Number.POSITIVE_INFINITY,
            }
      }
    >
      {children}
    </MotionComponent>
  );
};

export const Shimmer = memo(ShimmerComponent);
