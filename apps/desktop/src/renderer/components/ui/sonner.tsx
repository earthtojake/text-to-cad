import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react"
import { Toaster as Sonner, type ToasterProps } from "sonner"

// shadcn ships this component reading `next-themes`. text-to-cad owns its theme
// in the settings store (system/light/dark, applied as a `.dark` class on
// <html>), so it reads that instead and `next-themes` is not a dependency.
import { useResolvedTheme } from "@renderer/hooks/use-theme"
import { isMac } from "@renderer/lib/platform"

// A module constant: sonner's keydown effect depends on the array, so a fresh one per
// render had it remove and re-add its listener every time the Toaster re-rendered.
//
// Cmd+Option+T on a Mac. Elsewhere Ctrl+Alt+T is GNOME's terminal and Windows delivers
// AltGr as Ctrl+Alt, so a Polish or German keyboard's AltGr+T would pull focus out of a field;
// Ctrl+Shift+T types nothing, is free in `lib/shortcuts.ts` and sits beside Ctrl+T (new tab).
const HOTKEY = isMac ? ["metaKey", "altKey", "KeyT"] : ["ctrlKey", "shiftKey", "KeyT"]

const Toaster = ({ ...props }: ToasterProps) => {
  const theme = useResolvedTheme()

  return (
    <Sonner
      theme={theme}
      className="toaster group"
      // Deliberate edit to the vendored component: stock is Alt+T, and Option+T types "†" on a
      // Mac keyboard, so the toast list stole focus from a sentence being typed. Mod+Alt+T types
      // nothing, and sits beside Mod+Alt+B (toggle explorer). `customAriaLabel`, because the
      // region's stock name appends the hotkey's key names ("Notifications metaKey+altKey+T").
      hotkey={HOTKEY}
      customAriaLabel="Notifications"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
