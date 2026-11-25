import * as React from "react"
import { Slider as SliderPrimitive } from "radix-ui"

import { cn } from "@cad/ui/utils"

// shadcn's slider: every slider in the viewer is this one (a row may size and place it). A slider
// with an `origin` (Position's joints: a joint's rest is mostly mid-range) fills from that value to
// the thumb, a tick at the origin, where shadcn's fills from its left end. Its shape is shadcn's at the
// viewer's denser scale (a 6px track, a 12px thumb, not 16px); its colours are quiet, as Figma's sliders
// are, from the `--slider-*` tokens (`styles/tokens.css`, light and dark): a faint neutral track, a fill
// a few steps darker (never the primary's near-black bar or the accent), a light thumb held off the panel
// by a thin ring and a small shadow. Hover strengthens the fill a step and the ring; the keyboard's focus
// rings the thumb; disabled, the whole slider is at half strength, its thumb flat. It adds only the
// rounding below.

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
  origin,
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
        "cad-hit group/slider relative flex w-full touch-none items-center select-none data-[disabled]:opacity-50 data-[orientation=vertical]:h-full data-[orientation=vertical]:min-h-44 data-[orientation=vertical]:w-auto data-[orientation=vertical]:flex-col",
        className
      )}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className={cn(
          "relative grow overflow-hidden rounded-full bg-(--slider-track) data-[orientation=horizontal]:h-1.5 data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-1.5"
        )}
      >
        {Number.isFinite(origin) && max > min ? <OriginFill origin={origin} value={values[0]} min={min} max={max} /> : <SliderPrimitive.Range
          data-slot="slider-range"
          className={cn(
            "absolute bg-(--slider-fill) transition-colors group-hover/slider:bg-(--slider-fill-hover) group-data-[disabled]/slider:bg-(--slider-fill) data-[orientation=horizontal]:h-full data-[orientation=vertical]:w-full"
          )}
        />}
      </SliderPrimitive.Track>
      {values.map((_, index) => (
        <SliderPrimitive.Thumb
          {...thumbProps}
          data-slot="slider-thumb"
          key={index}
          className="block size-thumb shrink-0 rounded-full border border-(--slider-thumb-border) bg-(--slider-thumb) shadow-(--slider-thumb-shadow) ring-ring/40 transition-[border-color,box-shadow] group-hover/slider:border-foreground/60 focus-visible:ring-[3px] focus-visible:outline-hidden group-data-[disabled]/slider:shadow-none data-[disabled]:pointer-events-none"
        />
      ))}
    </SliderPrimitive.Root>
  )
}

// A horizontal slider's fill from `origin` to its value, and a tick at the origin where it is inside the range.
function OriginFill({ origin, value, min, max }) {
  const at = number => Math.min(100, Math.max(0, ((Number(number) - min) / (max - min)) * 100))
  const from = at(origin), to = at(value)
  return <>
    <span data-slot="slider-fill" className="absolute h-full bg-(--slider-fill) transition-colors group-hover/slider:bg-(--slider-fill-hover) group-data-[disabled]/slider:bg-(--slider-fill)" style={{ left: `${Math.min(from, to)}%`, width: `${Math.abs(to - from)}%` }} />
    {from > 0 && from < 100 ? <span data-slot="slider-origin" className="absolute inset-y-0 w-px bg-foreground/40" style={{ left: `calc(${from}% - 0.5px)` }} /> : null}
  </>
}

export { Slider }
