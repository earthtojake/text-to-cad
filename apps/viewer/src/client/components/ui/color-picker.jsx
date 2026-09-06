import * as React from "react"
import { Pipette } from "lucide-react"

import { cn } from "@/ui/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/
const FORMAT_OPTIONS = ["hex", "rgb", "hsl"]

function clamp(value, min, max) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) {
    return min
  }
  return Math.min(Math.max(numericValue, min), max)
}

function normalizeHexColor(value, fallback = "#ffffff") {
  const rawValue = String(value || "").trim()
  if (!HEX_COLOR_PATTERN.test(rawValue)) {
    return fallback
  }
  if (rawValue.length === 4) {
    return `#${rawValue[1]}${rawValue[1]}${rawValue[2]}${rawValue[2]}${rawValue[3]}${rawValue[3]}`.toLowerCase()
  }
  return rawValue.toLowerCase()
}

function componentToHex(value) {
  return Math.round(clamp(value, 0, 255)).toString(16).padStart(2, "0")
}

function rgbToHex({ r, g, b }) {
  return `#${componentToHex(r)}${componentToHex(g)}${componentToHex(b)}`.toLowerCase()
}

function hexToRgb(value) {
  const hex = normalizeHexColor(value)
  return {
    r: parseInt(hex.slice(1, 3), 16),
    g: parseInt(hex.slice(3, 5), 16),
    b: parseInt(hex.slice(5, 7), 16)
  }
}

function rgbToHsv({ r, g, b }) {
  const red = clamp(r, 0, 255) / 255
  const green = clamp(g, 0, 255) / 255
  const blue = clamp(b, 0, 255) / 255
  const max = Math.max(red, green, blue)
  const min = Math.min(red, green, blue)
  const delta = max - min
  let h = 0

  if (delta !== 0) {
    if (max === red) {
      h = ((green - blue) / delta) % 6
    } else if (max === green) {
      h = (blue - red) / delta + 2
    } else {
      h = (red - green) / delta + 4
    }
    h *= 60
    if (h < 0) {
      h += 360
    }
  }

  return {
    h,
    s: max === 0 ? 0 : (delta / max) * 100,
    v: max * 100
  }
}

function hsvToRgb({ h, s, v }) {
  const hue = ((Number(h) % 360) + 360) % 360
  const saturation = clamp(s, 0, 100) / 100
  const value = clamp(v, 0, 100) / 100
  const chroma = value * saturation
  const secondary = chroma * (1 - Math.abs(((hue / 60) % 2) - 1))
  const match = value - chroma
  let red = 0
  let green = 0
  let blue = 0

  if (hue < 60) {
    red = chroma
    green = secondary
  } else if (hue < 120) {
    red = secondary
    green = chroma
  } else if (hue < 180) {
    green = chroma
    blue = secondary
  } else if (hue < 240) {
    green = secondary
    blue = chroma
  } else if (hue < 300) {
    red = secondary
    blue = chroma
  } else {
    red = chroma
    blue = secondary
  }

  return {
    r: (red + match) * 255,
    g: (green + match) * 255,
    b: (blue + match) * 255
  }
}

function rgbToHsl({ r, g, b }) {
  const red = clamp(r, 0, 255) / 255
  const green = clamp(g, 0, 255) / 255
  const blue = clamp(b, 0, 255) / 255
  const max = Math.max(red, green, blue)
  const min = Math.min(red, green, blue)
  const delta = max - min
  let h = 0
  let s = 0
  const l = (max + min) / 2

  if (delta !== 0) {
    s = delta / (1 - Math.abs((2 * l) - 1))
    if (max === red) {
      h = ((green - blue) / delta) % 6
    } else if (max === green) {
      h = (blue - red) / delta + 2
    } else {
      h = (red - green) / delta + 4
    }
    h *= 60
    if (h < 0) {
      h += 360
    }
  }

  return {
    h,
    s: s * 100,
    l: l * 100
  }
}

function hslToRgb({ h, s, l }) {
  const hue = ((Number(h) % 360) + 360) % 360
  const saturation = clamp(s, 0, 100) / 100
  const lightness = clamp(l, 0, 100) / 100
  const chroma = (1 - Math.abs((2 * lightness) - 1)) * saturation
  const secondary = chroma * (1 - Math.abs(((hue / 60) % 2) - 1))
  const match = lightness - (chroma / 2)
  let red = 0
  let green = 0
  let blue = 0

  if (hue < 60) {
    red = chroma
    green = secondary
  } else if (hue < 120) {
    red = secondary
    green = chroma
  } else if (hue < 180) {
    green = chroma
    blue = secondary
  } else if (hue < 240) {
    green = secondary
    blue = chroma
  } else if (hue < 300) {
    red = secondary
    blue = chroma
  } else {
    red = chroma
    blue = secondary
  }

  return {
    r: (red + match) * 255,
    g: (green + match) * 255,
    b: (blue + match) * 255
  }
}

function roundedColorNumbers(hex) {
  const rgb = hexToRgb(hex)
  const hsl = rgbToHsl(rgb)
  return {
    rgb,
    hsl: {
      h: Math.round(hsl.h),
      s: Math.round(hsl.s),
      l: Math.round(hsl.l)
    },
    hsv: rgbToHsv(rgb)
  }
}

function ColorNumberInput({ label, value, min, max, onChange }) {
  return (
    <label className="min-w-0 space-y-1">
      <span className="block text-micro uppercase tracking-[0.08em] text-muted-foreground">
        {label}
      </span>
      <Input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(clamp(event.currentTarget.value, min, max))}
        className="h-7 px-1.5 text-tiny"
      />
    </label>
  )
}

function ColorPicker({
  value = "#ffffff",
  onChange,
  opacity = 1,
  onOpacityChange,
  className,
  swatchClassName,
  valueClassName,
  popoverAlign = "start",
  showValue = true,
  showOpacity = false,
  disabled = false,
  ...props
}) {
  const normalizedValue = normalizeHexColor(value)
  const normalizedOpacity = Number.isFinite(Number(opacity)) ? clamp(Number(opacity), 0, 1) : 1
  const [format, setFormat] = React.useState("hex")
  const [hexDraft, setHexDraft] = React.useState(normalizedValue)
  const [canUseEyeDropper, setCanUseEyeDropper] = React.useState(false)
  const svPlaneRef = React.useRef(null)
  const hueTrackRef = React.useRef(null)

  React.useEffect(() => {
    setHexDraft(normalizedValue)
  }, [normalizedValue])

  React.useEffect(() => {
    setCanUseEyeDropper(typeof window !== "undefined" && typeof window.EyeDropper === "function")
  }, [])

  const colorNumbers = React.useMemo(() => roundedColorNumbers(normalizedValue), [normalizedValue])
  const hue = colorNumbers.hsv.h
  const svColor = `hsl(${hue} 100% 50%)`

  const commitHex = React.useCallback((nextHex) => {
    const normalizedNextHex = normalizeHexColor(nextHex, normalizedValue)
    setHexDraft(normalizedNextHex)
    if (normalizedNextHex !== normalizedValue) {
      onChange?.(normalizedNextHex)
    }
  }, [normalizedValue, onChange])

  const updateFromSvPointer = React.useCallback((event) => {
    const rect = svPlaneRef.current?.getBoundingClientRect()
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      return
    }
    const nextS = clamp(((event.clientX - rect.left) / rect.width) * 100, 0, 100)
    const nextV = clamp((1 - ((event.clientY - rect.top) / rect.height)) * 100, 0, 100)
    commitHex(rgbToHex(hsvToRgb({ h: hue, s: nextS, v: nextV })))
  }, [commitHex, hue])

  const updateFromHuePointer = React.useCallback((event) => {
    const rect = hueTrackRef.current?.getBoundingClientRect()
    if (!rect || rect.width <= 0) {
      return
    }
    const nextHue = clamp(((event.clientX - rect.left) / rect.width) * 360, 0, 360)
    commitHex(rgbToHex(hsvToRgb({
      h: nextHue,
      s: colorNumbers.hsv.s,
      v: colorNumbers.hsv.v
    })))
  }, [colorNumbers.hsv.s, colorNumbers.hsv.v, commitHex])

  const handleSvPointerDown = (event) => {
    svPlaneRef.current?.setPointerCapture(event.pointerId)
    updateFromSvPointer(event)
  }

  const handleHuePointerDown = (event) => {
    hueTrackRef.current?.setPointerCapture(event.pointerId)
    updateFromHuePointer(event)
  }

  const handleHexCommit = (nextValue) => {
    if (!HEX_COLOR_PATTERN.test(String(nextValue || "").trim())) {
      setHexDraft(normalizedValue)
      return
    }
    commitHex(nextValue)
  }

  const setRgbChannel = (channel, nextValue) => {
    commitHex(rgbToHex({
      ...colorNumbers.rgb,
      [channel]: nextValue
    }))
  }

  const setHslChannel = (channel, nextValue) => {
    commitHex(rgbToHex(hslToRgb({
      ...colorNumbers.hsl,
      [channel]: nextValue
    })))
  }

  const pickFromScreen = async () => {
    if (!canUseEyeDropper) {
      return
    }
    try {
      const result = await new window.EyeDropper().open()
      if (result?.sRGBHex) {
        commitHex(result.sRGBHex)
      }
    } catch {
      // The browser throws when the user cancels the eyedropper; no UI state changes are needed.
    }
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          data-slot="color-picker-trigger"
          variant="outline"
          size="sm"
          disabled={disabled}
          className={cn("h-7 w-auto max-w-full justify-start gap-1.5 px-1.5 text-tiny", className)}
          {...props}
        >
          <span
            className={cn(
              "size-4 shrink-0 rounded bg-clip-border shadow-[0_0_0_1px_rgba(15,23,42,0.24)] dark:shadow-[0_0_0_1px_rgba(255,255,255,0.24)]",
              swatchClassName
            )}
            style={{
              backgroundColor: normalizedValue,
              opacity: showOpacity ? normalizedOpacity : undefined
            }}
            aria-hidden="true"
          />
          {showValue ? (
            <span className={cn("truncate font-mono uppercase leading-none", valueClassName)}>{normalizedValue}</span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align={popoverAlign} className="w-64 space-y-3 p-3">
        <div
          ref={svPlaneRef}
          role="slider"
          tabIndex={0}
          aria-label="Saturation and brightness"
          aria-valuetext={`${Math.round(colorNumbers.hsv.s)}% saturation, ${Math.round(colorNumbers.hsv.v)}% brightness`}
          className="relative h-32 touch-none overflow-hidden rounded-md border shadow-inner outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          style={{
            backgroundColor: svColor,
            backgroundImage: "linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, transparent)"
          }}
          onPointerDown={handleSvPointerDown}
          onPointerMove={(event) => {
            if (svPlaneRef.current?.hasPointerCapture(event.pointerId)) {
              updateFromSvPointer(event)
            }
          }}
        >
          <span
            className="absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-[0_0_0_1px_rgba(0,0,0,0.45)]"
            style={{
              left: `${colorNumbers.hsv.s}%`,
              top: `${100 - colorNumbers.hsv.v}%`
            }}
            aria-hidden="true"
          />
        </div>

        <div
          ref={hueTrackRef}
          role="slider"
          tabIndex={0}
          aria-label="Hue"
          aria-valuemin={0}
          aria-valuemax={360}
          aria-valuenow={Math.round(hue)}
          className="relative h-3 touch-none rounded-full border outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
          style={{
            background: "linear-gradient(90deg, #f00, #ff0, #0f0, #0ff, #00f, #f0f, #f00)"
          }}
          onPointerDown={handleHuePointerDown}
          onPointerMove={(event) => {
            if (hueTrackRef.current?.hasPointerCapture(event.pointerId)) {
              updateFromHuePointer(event)
            }
          }}
        >
          <span
            className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-[0_0_0_1px_rgba(0,0,0,0.45)]"
            style={{ left: `${(hue / 360) * 100}%`, backgroundColor: svColor }}
            aria-hidden="true"
          />
        </div>

        {showOpacity ? (
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2 text-micro uppercase tracking-[0.08em] text-muted-foreground">
              <span>Opacity</span>
              <span>{Math.round(normalizedOpacity * 100)}%</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Input
                type="number"
                min={0}
                max={100}
                step={1}
                value={Math.round(normalizedOpacity * 100)}
                onChange={(event) => {
                  onOpacityChange?.(clamp(event.currentTarget.value, 0, 100) / 100)
                }}
                className="h-7 px-1.5 text-tiny"
                aria-label="Color opacity"
              />
              <span className="text-micro text-muted-foreground">%</span>
            </div>
          </div>
        ) : null}

        <div className="flex items-center gap-1 rounded-md bg-muted p-1">
          {FORMAT_OPTIONS.map((option) => (
            <Button
              key={option}
              type="button"
              variant={format === option ? "secondary" : "ghost"}
              size="xs"
              className="h-6 flex-1 px-2 text-micro uppercase"
              onClick={() => setFormat(option)}
            >
              {option}
            </Button>
          ))}
        </div>

        {format === "hex" ? (
          <div className="flex gap-2">
            <Input
              value={hexDraft}
              onChange={(event) => setHexDraft(event.currentTarget.value)}
              onBlur={(event) => handleHexCommit(event.currentTarget.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  handleHexCommit(event.currentTarget.value)
                }
              }}
              className="h-7 px-1.5 text-tiny font-mono uppercase"
              aria-label="Hex color"
            />
            {canUseEyeDropper ? (
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                onClick={pickFromScreen}
                aria-label="Pick color from screen"
                title="Pick color from screen"
              >
                <Pipette className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              </Button>
            ) : null}
          </div>
        ) : null}

        {format === "rgb" ? (
          <div className="grid grid-cols-3 gap-2">
            <ColorNumberInput label="R" value={colorNumbers.rgb.r} min={0} max={255} onChange={(nextValue) => setRgbChannel("r", nextValue)} />
            <ColorNumberInput label="G" value={colorNumbers.rgb.g} min={0} max={255} onChange={(nextValue) => setRgbChannel("g", nextValue)} />
            <ColorNumberInput label="B" value={colorNumbers.rgb.b} min={0} max={255} onChange={(nextValue) => setRgbChannel("b", nextValue)} />
          </div>
        ) : null}

        {format === "hsl" ? (
          <div className="grid grid-cols-3 gap-2">
            <ColorNumberInput label="H" value={colorNumbers.hsl.h} min={0} max={360} onChange={(nextValue) => setHslChannel("h", nextValue)} />
            <ColorNumberInput label="S" value={colorNumbers.hsl.s} min={0} max={100} onChange={(nextValue) => setHslChannel("s", nextValue)} />
            <ColorNumberInput label="L" value={colorNumbers.hsl.l} min={0} max={100} onChange={(nextValue) => setHslChannel("l", nextValue)} />
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}

export { ColorPicker }
