import { cn } from "../lib/utils.js"
import { Loader2Icon } from "lucide-react"
import { useI18n } from "../i18n/index.js"

function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  const { t } = useI18n()
  return (
    <Loader2Icon
      role="status"
      aria-label={t("spinner.loading")}
      className={cn("size-4 animate-spin", className)}
      {...props}
    />
  )
}

export { Spinner }
