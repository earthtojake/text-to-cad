import * as React from "react"
import { Slider as SliderPrimitive } from "radix-ui"

import { cn } from "@hardcore/ui/utils"

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
          "relative grow overflow-hidden rounded-full bg-muted data-[orientation=horizontal]:h-1 data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-1"
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
          className="relative z-10 block size-3.5 shrink-0 rounded-full border border-background bg-primary shadow-sm ring-1 ring-foreground/15 transition-[color,box-shadow] outline-none hover:ring-2 hover:ring-ring/25 focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50"
        />
      ))}
    </SliderPrimitive.Root>
  )
}

export { Slider }
