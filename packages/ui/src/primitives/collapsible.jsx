import * as React from "react"
import { Collapsible as CollapsiblePrimitive } from "radix-ui"

function Collapsible({
  ...props
}) {
  return <CollapsiblePrimitive.Root data-slot="collapsible" {...props} />;
}

const CollapsibleTrigger = React.forwardRef(function CollapsibleTrigger({
  ...props
}, ref) {
  return (<CollapsiblePrimitive.CollapsibleTrigger ref={ref} data-slot="collapsible-trigger" {...props} />);
});

const CollapsibleContent = React.forwardRef(function CollapsibleContent({
  ...props
}, ref) {
  return (<CollapsiblePrimitive.CollapsibleContent ref={ref} data-slot="collapsible-content" {...props} />);
});

export { Collapsible, CollapsibleTrigger, CollapsibleContent }
