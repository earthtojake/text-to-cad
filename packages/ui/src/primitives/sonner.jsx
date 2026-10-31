"use client"

import { useContext } from "react"
import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react"
import { Toaster as Sonner } from "sonner"

import { ViewerHostContext } from "../host/context.js"

// shadcn's sonner, as shadcn ships it; its theme is the viewer host's colour scheme
// (`environment.colorScheme`) in place of next-themes' `useTheme`.
const Toaster = ({ ...props }) => {
  const theme = useContext(ViewerHostContext)?.environment.colorScheme ?? "system"

  return (
    <Sonner
      theme={theme}
      className="toaster group"
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
        }
      }
      {...props}
    />
  )
}

export { Toaster }
