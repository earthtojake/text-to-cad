import { useState } from "react";
import LoadingIcon from "@hardcore/ui/loading-icon";

/** The native GLB mark uses its existing loop only while hovered. */
export default function ViewerBrand() {
  const [hovered, setHovered] = useState(false);
  return <span aria-hidden="true" className="mr-1 size-5 shrink-0"
    onPointerEnter={() => setHovered(true)} onPointerLeave={() => setHovered(false)}>
    <LoadingIcon size={20} active={hovered} />
  </span>;
}
