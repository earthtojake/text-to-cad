// One class-merging implementation for the whole renderer. shadcn's current
// registry output imports `cn` from the `cn` package directly; the vendored
// AI Elements import it from here. Same function either way.
export { cn, type ClassValue } from "cn";
