import * as React from "react"
import { Slider as SliderPrimitive } from "radix-ui"

import { cn } from "@text-to-cad/ui/utils"

// shadcn's slider: every slider in the viewer is this one (a row may size and place it; Position's
// joints leave out its fill). Two changes from shadcn's, for the viewer's denser, see-through
// panels (11px text, 24px rows): a 12px thumb, not 16px, and a track a shade darker than muted,
// which all but vanishes on a translucent panel. It adds only the rounding below.

// The decimals a step is written with ("0.25" → 2): what a reported value is rounded to.
function stepDecimals(step) {
  const text = String(step)
  const exponent = text.match(/e-(\d+)$/)
  return Math.min(10, exponent ? Number(exponent[1]) : (text.split(".")[1] || "").length)
}

/**
 * A value arrives as a sum of floats (a percentage of a range, a pose in degrees), and the thumb
 * would announce it as `28.000000000000004`: each value is rounded to the precision of `step`, so
 * `aria-valuenow` reads what the field beside it shows.
 */
function Slider({
  className,
  defaultValue,
  value: rawValue,
  min = 0,
  max = 100,
  step = 1,
  thumbProps,
  ...props
}) {
  const decimals = stepDecimals(step)
  const value = React.useMemo(
    () => Array.isArray(rawValue) ? rawValue.map(item => Number.isFinite(Number(item)) ? Number(Number(item).toFixed(decimals)) : item) : rawValue,
    [rawValue, decimals]
  )
  const values = React.useMemo(
    () =>
      Array.isArray(value)
        ? value
        : Array.isArray(defaultValue)
          ? defaultValue
          : [min],
    [defaultValue, min, value]
  )

  return (
    <SliderPrimitive.Root
      data-slot="slider"
      defaultValue={defaultValue}
      value={value}
      min={min}
      max={max}
      step={step}
      className={cn(
        "relative flex w-full touch-none items-center select-none data-[disabled]:opacity-50 data-[orientation=vertical]:h-full data-[orientation=vertical]:min-h-44 data-[orientation=vertical]:w-auto data-[orientation=vertical]:flex-col",
        className
      )}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className={cn(
          "relative grow overflow-hidden rounded-full bg-foreground/15 data-[orientation=horizontal]:h-1.5 data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-1.5"
        )}
      >
        <SliderPrimitive.Range
          data-slot="slider-range"
          className={cn(
            "absolute bg-primary data-[orientation=horizontal]:h-full data-[orientation=vertical]:w-full"
          )}
        />
      </SliderPrimitive.Track>
      {values.map((_, index) => (
        <SliderPrimitive.Thumb
          {...thumbProps}
          data-slot="slider-thumb"
          key={index}
          className="block size-3 shrink-0 rounded-full border border-primary bg-white shadow-sm ring-ring/50 transition-[color,box-shadow] hover:ring-4 focus-visible:ring-4 focus-visible:outline-hidden disabled:pointer-events-none disabled:opacity-50"
        />
      ))}
    </SliderPrimitive.Root>
  )
}

export { Slider }
