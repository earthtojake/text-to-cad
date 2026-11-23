import { Switch as SwitchPrimitive } from "radix-ui"

import { cn } from "@cad/ui/utils"

/** shadcn's switch at the chrome's scale (`--cad-switch-h`, `--cad-switch-w`: 24×14 on a desktop, 36×20 on a phone), the primary colour while on. */
function Switch({ className, ...props }) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "peer inline-flex h-(--cad-switch-h) w-(--cad-switch-w) shrink-0 items-center rounded-full border border-transparent shadow-xs outline-none transition-all",
        "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
        "data-[state=checked]:bg-primary data-[state=unchecked]:bg-muted-foreground/35",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block size-[calc(var(--cad-switch-h)-2px)] rounded-full bg-background ring-0 transition-transform data-[state=checked]:translate-x-[calc(100%-2px)] data-[state=unchecked]:translate-x-0 dark:data-[state=checked]:bg-primary-foreground dark:data-[state=unchecked]:bg-foreground"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
