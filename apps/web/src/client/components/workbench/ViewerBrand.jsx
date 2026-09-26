import { useState } from "react";
import LoadingIcon from "@hardcore/ui/loading-icon";

/** The icon at the head of the nav row, and the app's name beside it while no file is open. */
export default function ViewerBrand({ title = "" }) {
  const [hovered, setHovered] = useState(false);
  return <>
    <span aria-hidden="true" className="mr-1 size-5 shrink-0"
      onPointerEnter={() => setHovered(true)} onPointerLeave={() => setHovered(false)}>
      <LoadingIcon size={20} active={hovered} />
    </span>
    {title ? <span className="truncate text-foreground" data-viewer-title="">{title}</span> : null}
  </>;
}
