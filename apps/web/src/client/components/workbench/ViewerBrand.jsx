import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import logoUrl from "../../assets/logo-c.svg";

/**
 * The C brand mark remains visible while a file loads; with a file open, it is the way home.
 * @param {{ onHome?: () => void }} props
 */
export default function ViewerBrand({ onHome }) {
  if (!onHome) {
    return <img src={logoUrl} alt="CAD" width={20} height={20} className="mr-1 size-5 shrink-0 object-contain" />;
  }
  return <TooltipHint content="Home">
    <button type="button" aria-label="CAD home" onClick={onHome}
      className="mr-1 flex shrink-0 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <img src={logoUrl} alt="" width={20} height={20} className="size-5 shrink-0 object-contain" />
    </button>
  </TooltipHint>;
}
